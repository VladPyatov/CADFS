import argparse
import json
import logging
import threading
from pathlib import Path
from typing import List, Optional

from src.api.account import AccountQueue
from src.logging_config import setup_logging
from src.rendering.session import render_files_with_api_session

setup_logging()
logger = logging.getLogger(__name__)


def process_files(
    files: List[Path],
    input_dir: Path,
    output_dir: Path,
    account_queue: AccountQueue,
    thread_id: int,
    export: bool,
) -> None:
    """
    Process files assigned to this thread.
    """
    logger.info(f'Starting with {len(files)} files')

    file_index = 0
    total_processed = 0

    while file_index < len(files):
        # Get account from queue
        account = account_queue.get_account(timeout=5.0)
        if account is None:
            logger.warning('No accounts available, stopping')
            break
        logger.info(f'Got account {account.access_key} with {account.remaining_quota()} quota')

        remaining_files = len(files) - file_index
        # Other option: min(account.remaining_quota(), remaining_files)
        files_to_process = min(128, remaining_files)
        # Get the slice of files for this session
        session_files = files[file_index : file_index + files_to_process]
        # Process files within session
        processed = render_files_with_api_session(session_files, input_dir, output_dir, account, thread_id, export)
        file_index += processed
        total_processed += processed
        # Return account if it has remaining quota
        if account.has_quota():
            account_queue.return_account(account)
            logger.info(f'Returned account {account.access_key} with {account.remaining_quota()} requests remaining')

    logger.info(f'Completed. Processed {total_processed}/{len(files)} files')


def process_chunk(
    chunk_num: Optional[int],
    input_dir: Path,
    output_dir: Path,
    account_queue: AccountQueue,
    num_threads: int = 4,
    export: bool = False,
) -> None:
    """
    Process all files in a chunk directory using multiple threads.
    """
    if chunk_num is None:
        chunk_dir = input_dir
    else:
        (output_dir / f'{chunk_num:04}').mkdir(exist_ok=True)
        chunk_dir = input_dir / f'{chunk_num:04}'
    # Get all code files
    raw_files = list(chunk_dir.glob('????????.txt'))
    # Fallback
    if len(raw_files) == 0:
        raw_files = list(chunk_dir.glob('????_????????.txt'))
    if len(raw_files) == 0:
        raw_files = list(chunk_dir.glob('?????_????????_????.txt'))
    if not raw_files:
        logger.warning(f'No files found in {chunk_dir}')
        return
    if chunk_num is None:
        raw_files = sorted([file.relative_to(chunk_dir) for file in raw_files])
    else:
        raw_files = sorted([file.relative_to(chunk_dir.parent) for file in raw_files])
    # Filter files to get only not processed ones
    files = []
    for file in raw_files:
        document_name = file.stem
        if chunk_num is None:
            doc_chunk = ''
        else:
            doc_chunk = file.parts[0]
        already_done = (output_dir / doc_chunk / f'{document_name}_ok.txt').exists() or (
            output_dir / doc_chunk / f'{document_name}.step'
        ).exists()
        if not export and already_done:
            continue
        if export and (output_dir / doc_chunk / f'{document_name}.step').exists():
            continue
        if (output_dir / doc_chunk / f'{document_name}_c.txt').exists():
            continue
        if (output_dir / doc_chunk / f'{document_name}_r.txt').exists():
            continue
        files.append(file)
    if not files:
        logger.warning(f'All files already processed {chunk_dir}')
        return
    logger.info(f'Processing {chunk_dir.name} with {len(files)} files using {num_threads} threads')
    # Split files among threads
    files_per_thread = len(files) // num_threads
    remainder = len(files) % num_threads
    file_groups = []
    start_idx = 0
    for i in range(num_threads):
        count = files_per_thread + (1 if i < remainder else 0)
        if count > 0:
            file_groups.append(files[start_idx : start_idx + count])
            start_idx += count
    # Create and start threads
    threads = []
    for i, file_group in enumerate(file_groups):
        thread = threading.Thread(
            target=process_files, args=(file_group, input_dir, output_dir, account_queue, i, export), name=f'Worker-{i}'
        )
        threads.append(thread)
        thread.start()
    for thread in threads:
        thread.join()


def main():
    """
    FeatureScript rendering
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--input_dir', type=str, help='Input dir')
    parser.add_argument('-o', '--output_dir', type=str, help='Output dir')
    parser.add_argument('-s', '--start', type=int, default=0, help='Start chunk number, pass -1 to process directory')
    parser.add_argument('-e', '--end', type=int, default=99, help='End chunk number')
    parser.add_argument('-w', '--workers', type=int, default=4, help='Number of parallel workers W, W <= 4')
    parser.add_argument('-c', '--creds', type=str, default='creds/onshape_accounts.json', help='Creds, json or dir')
    parser.add_argument('-r', '--rendering', action='store_true', help='Use this flag to export models in step format')
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    creds = Path(args.creds)
    output_dir.mkdir(exist_ok=True)
    start_chunk, end_chunk = args.start, args.end
    num_threads = args.workers

    if not creds.exists():
        print(f'Credentials path is invalid: {creds}')
        exit()
    if creds.is_file():
        with open(creds) as f:
            accounts = list(json.load(f).items())
    else:
        accounts = []
        available_keys = sorted(filter(lambda p: p.suffix == '.json', creds.iterdir()))
        for key_path in available_keys:
            with open(key_path) as f:
                key = json.load(f)['https://cad.onshape.com']
                accounts.append((key['access_key'], key['secret_key']))

    account_queue = AccountQueue(accounts)
    logger.info(f'Initialized {len(accounts)} accounts')
    chunks_to_process = [None] if start_chunk == -1 else range(start_chunk, end_chunk + 1)
    for chunk_num in chunks_to_process:
        label = 'flat directory' if chunk_num is None else f'{chunk_num}/{end_chunk}'
        logger.info(f'\n{"=" * 50}')
        logger.info(f'Processing chunk {label}')
        logger.info(f'{"=" * 50}')

        process_chunk(chunk_num, input_dir, output_dir, account_queue, num_threads, args.rendering)
        logger.info(f'Chunk {label} complete')

        if account_queue.is_empty() and chunk_num is not None and chunk_num < end_chunk:
            logger.warning('All account quotas exhausted, stopping')
            break

    logger.info(f'\n{"=" * 50}')
    logger.info('Processing Complete')
    logger.info(f'{"=" * 50}')
    # Verify all input files were processed
    total_input = 0
    total_processed = 0
    for chunk_num in chunks_to_process:
        chunk_dir = input_dir if chunk_num is None else input_dir / f'{chunk_num:04}'
        raw_files = list(chunk_dir.glob('????????.txt'))
        if not raw_files:
            raw_files = list(chunk_dir.glob('????_????????.txt'))
        if not raw_files:
            raw_files = list(chunk_dir.glob('?????_????????_????.txt'))
        if chunk_num is None:
            raw_files = [f.relative_to(chunk_dir) for f in raw_files]
        else:
            raw_files = [f.relative_to(chunk_dir.parent) for f in raw_files]
        total_input += len(raw_files)
        for file in raw_files:
            name = file.stem
            doc_chunk = '' if chunk_num is None else file.parts[0]
            out = output_dir / doc_chunk
            if any(
                p.exists()
                for p in [
                    out / f'{name}_ok.txt',
                    out / f'{name}.step',
                    out / f'{name}_c.txt',
                    out / f'{name}_r.txt',
                ]
            ):
                total_processed += 1
    logger.info(f'Files processed: {total_processed}/{total_input}')
    if total_processed < total_input:
        logger.warning(
            f'{total_input - total_processed} files were not processed. '
            'Just run the script again to automatically process remaining files'
        )


if __name__ == '__main__':
    main()
