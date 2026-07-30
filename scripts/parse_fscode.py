import argparse
import logging
import multiprocessing as mp
import os
import pathlib
import sys
import traceback
from collections import Counter

from tqdm import tqdm

_PROJECT_ROOT = str(pathlib.Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.fs_parser.exceptions import (  # noqa: E402
    EmptyGeometryError,
    ForeignGeometryError,
    MissingSketchInfoError,
    NotImplementedOperationError,
    NotImplementedQueryError,
    ParserError,
)
from src.fs_parser.parser import Parser  # noqa: E402
from src.fs_parser.values import set_default_tolerance  # noqa: E402
from src.logging_config import setup_logging  # noqa: E402

logger = logging.getLogger(__name__)

_UNSUPPORTED_REASON = {
    ForeignGeometryError: 'foreign',
    EmptyGeometryError: 'empty',
    NotImplementedOperationError: 'unsupported_op',
    NotImplementedQueryError: 'unsupported_query',
    MissingSketchInfoError: 'missing_sketch',
}


def run(fs_part_dir: str, sketch_part_dir: str, output_part_dir: str, sample: str) -> str:
    """Parse one sample and write its cleaned `.txt`.

    Returns a status: 'ok'; one of the expected-skip reasons ('foreign', 'empty',
    'unsupported_op', 'unsupported_query', 'missing_sketch', 'unsupported_other') when
    the parser intentionally declines the sample; or 'failed' for any genuine error.
    """
    txt_path = os.path.join(fs_part_dir, sample)
    info_path = os.path.join(sketch_part_dir, sample.replace('.txt', '.json'))

    try:
        cad_parser = Parser(txt_path, info_path)
        res, _ops = cad_parser.process_text()
        with open(os.path.join(output_part_dir, sample), 'w') as file:
            file.write(res)
        return 'ok'
    except (ParserError, NotImplementedError) as e:
        return _UNSUPPORTED_REASON.get(type(e), 'unsupported_other')
    except Exception as e:
        logger.error(f'{sample} failed: {e!r}')
        logger.debug(traceback.format_exc())
        return 'failed'


def _worker(kwargs: dict) -> str:
    """Picklable trampoline so `run` can be dispatched through mp.Pool with kwargs."""
    return run(**kwargs)


def parse_parallel(
    fs_dir: str,
    sketch_dir: str,
    output_dir: str,
    workers: int,
    start: int = None,
    stop: int = None,
    skip_existing: bool = False,
) -> Counter:
    os.makedirs(output_dir, exist_ok=True)
    parts = sorted(os.listdir(fs_dir))
    if start is not None and stop is not None:
        parts = parts[start:stop]

    stats: Counter = Counter()
    for part in tqdm(parts):
        fs_part_dir = os.path.join(fs_dir, part)
        sketch_part_dir = os.path.join(sketch_dir, part)
        output_part_dir = os.path.join(output_dir, part)
        os.makedirs(output_part_dir, exist_ok=True)

        jobs = []
        for sample in sorted(os.listdir(fs_part_dir)):
            if '.txt' not in sample:
                continue
            if skip_existing and os.path.exists(os.path.join(output_part_dir, sample)):
                stats['skipped'] += 1
                continue
            jobs.append(
                {
                    'fs_part_dir': fs_part_dir,
                    'sketch_part_dir': sketch_part_dir,
                    'output_part_dir': output_part_dir,
                    'sample': sample,
                }
            )

        if not jobs:
            continue
        with mp.Pool(workers) as pool:
            for status in pool.imap(_worker, jobs):
                stats[status] += 1

    total = sum(stats.values())
    logger.info(
        f'done: {total} samples — ok={stats["ok"]} failed={stats["failed"]} '
        f'skipped={stats["skipped"]} | unsupported: foreign={stats["foreign"]} '
        f'empty={stats["empty"]} op={stats["unsupported_op"]} '
        f'query={stats["unsupported_query"]} missing_sketch={stats["missing_sketch"]} '
        f'other={stats["unsupported_other"]}'
    )
    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--fs_dir', type=str, required=True, help='root of FeatureScript .txt samples')
    parser.add_argument('--sketch_dir', type=str, required=True, help='root of companion sketch-info .json')
    parser.add_argument('--output_dir', type=str, required=True)
    parser.add_argument('--start', type=int, default=None, help='slice start over sorted parts')
    parser.add_argument('--stop', type=int, default=None, help='slice stop over sorted parts')
    parser.add_argument('--workers', type=int, default=mp.cpu_count(), help='pool size (default: all cores)')
    parser.add_argument('--skip_existing', action='store_true', help='skip samples whose output .txt already exists')
    parser.add_argument('--tolerance', type=float, default=1e-2, help='long_round tolerance: 1e-10 or 1e-2')
    args = parser.parse_args()

    setup_logging()
    # Set before the pool is created so forked workers inherit the tolerance.
    set_default_tolerance(args.tolerance)
    parse_parallel(
        args.fs_dir,
        args.sketch_dir,
        args.output_dir,
        args.workers,
        args.start,
        args.stop,
        skip_existing=args.skip_existing,
    )


if __name__ == '__main__':
    main()
