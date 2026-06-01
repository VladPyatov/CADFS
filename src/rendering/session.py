import logging
import traceback
from pathlib import Path
from typing import List

from src.api.account import Account
from src.api.client import Client
from src.rendering.render import render_document

logger = logging.getLogger(__name__)


def render_files_with_api_session(
    files: List[Path],
    input_dir: Path,
    output_dir: Path,
    account: Account,
    thread_id: int,
    export: bool,
) -> int:
    """
    Process files using a single api session for the account.

    Returns:
        Number of files processed
    """
    files_processed = 0
    # Initialize client
    creds = {'access_key': account.access_key, 'secret_key': account.secret_key}
    os_client = Client(logging=False, version=12, creds=creds)
    # Create new document
    res = os_client.new_document(f'document_{thread_id}').json()
    logger.info(f'Session established for {account.access_key}')
    document_url = res['defaultWorkspace']['href']
    doc_id = document_url.split('/')[-3]
    ws_id = document_url.split('/')[-1]
    # Create part studio
    res = os_client.create_partstudio(doc_id, ws_id, 'PS_1').json()
    part_studio_id = res['id']
    # Create feature studio
    res = os_client.new_fs('FS_1', doc_id, ws_id).json()
    fs_id = res['id']
    # Process files with this session
    for filepath in files:
        if not account.has_quota():
            logger.info(f'Account {account.access_key} quota exhausted')
            break
        files_processed += 1
        finished = False
        failed = 0
        while not finished:
            try:
                remaining_quota = render_document(
                    os_client, input_dir, output_dir, filepath, doc_id, ws_id, part_studio_id, fs_id, export
                )
                account.update_remaining_quota(remaining_quota)
                finished = True
            except ConnectionError:
                failed += 1
                logger.warning(f'{filepath} - ConnectionError, trying again...')
            except Exception as ex:
                failed += 1
                logger.error(f'{filepath} - {repr(ex)}\n{traceback.format_exc()}')
            if failed == 3:
                logger.error(f'Failed to process {filepath} after 3 attempts')
                finished = True

        # Log progress
        if files_processed % 50 == 0:
            logger.info(f'Processed {files_processed} files, quota remaining: {account.remaining_quota()}')

    # remove created Part Studio and Feature Studio
    res = os_client.delete_element(doc_id, ws_id, fs_id)
    res = os_client.delete_element(doc_id, ws_id, part_studio_id)
    res = os_client.del_document(doc_id)

    logger.info(f'Processed {files_processed} files with account {account.access_key}')
    return files_processed
