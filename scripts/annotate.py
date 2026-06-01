#!/usr/bin/env python3
"""CLI entry point for generating FeatureScript annotations.

Uses a two-stage pipeline (generator + reviewer).
"""

import argparse
import logging
import pathlib
import sys

_PROJECT_ROOT = str(pathlib.Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from dotenv import load_dotenv  # noqa: E402

from src.annotations import process_folder  # noqa: E402
from src.logging_config import setup_logging  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description=(
            'Generate detailed English annotations for FeatureScript files using a two-stage pipeline '
            '(generator + reviewer).'
        )
    )
    parser.add_argument(
        '--input_dir',
        required=True,
        help='Path to folder containing FeatureScript .txt files',
    )
    parser.add_argument(
        '--output_dir',
        required=True,
        help='Path to folder where annotations (.txt) will be written',
    )
    parser.add_argument(
        '--logfire',
        action='store_true',
        help='Enable Logfire tracing if LOGFIRE_TOKEN is set',
    )
    parser.add_argument(
        '--quiet',
        '-q',
        action='store_true',
        help='Suppress verbose HTTP request logs',
    )

    args = parser.parse_args(argv)

    log_level = logging.WARNING if args.quiet else logging.INFO
    setup_logging(level=log_level)
    if args.quiet:
        logging.getLogger('httpx').setLevel(logging.WARNING)
        logging.getLogger('httpcore').setLevel(logging.WARNING)
        logging.getLogger('openai').setLevel(logging.WARNING)

    input_dir = pathlib.Path(args.input_dir).expanduser().resolve()
    output_dir = pathlib.Path(args.output_dir).expanduser().resolve()

    if not input_dir.exists() or not input_dir.is_dir():
        print(f'Input directory does not exist: {input_dir}', file=sys.stderr)
        return 2

    written = process_folder(
        input_dir=input_dir,
        output_dir=output_dir,
        enable_logfire=bool(args.logfire),
    )
    print(f'Wrote {len(written)} annotations to: {output_dir}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
