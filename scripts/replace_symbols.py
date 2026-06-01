#!/usr/bin/env python3
import argparse
import os
import shutil
import sys
import unicodedata
from typing import Iterable, Tuple

from tqdm import tqdm

HORIZONTAL_SPACE_CODEPOINTS = {
    '\u00a0',  # NO-BREAK SPACE
    '\u1680',  # OGHAM SPACE MARK
    '\u2000',  # EN QUAD
    '\u2001',  # EM QUAD
    '\u2002',  # EN SPACE
    '\u2003',  # EM SPACE
    '\u2004',  # THREE-PER-EM SPACE
    '\u2005',  # FOUR-PER-EM SPACE
    '\u2006',  # SIX-PER-EM SPACE
    '\u2007',  # FIGURE SPACE
    '\u2008',  # PUNCTUATION SPACE
    '\u2009',  # THIN SPACE
    '\u200a',  # HAIR SPACE
    '\u202f',  # NARROW NO-BREAK SPACE
    '\u205f',  # MEDIUM MATHEMATICAL SPACE
    '\u3000',  # IDEOGRAPHIC SPACE
    '\u200b',  # ZERO WIDTH SPACE
    '\u3000',  # IDEOGRAPHIC SPACE
}

DASH_LIKE_CODEPOINTS = {
    '\u2011',  # NON-BREAKING HYPHEN
    '\u2010',  # HYPHEN
    '\u2013',  # EN DASH
    '\u2014',  # EM DASH
    '\u2212',  # MINUS SIGN
}


def is_text_file(path: str, read_bytes: int = 2048) -> bool:
    try:
        with open(path, 'rb') as f:
            chunk = f.read(read_bytes)
        if not chunk:
            return True
        if b'\x00' in chunk:
            return False
        text = chunk.decode('utf-8', errors='replace')
        return text.count('\ufffd') / max(1, len(text)) < 0.2
    except Exception:
        return False


def replace_space_like(text: str) -> Tuple[str, int]:
    replaced = 0
    out_chars = []
    for ch in text:
        if ch in ('\n', '\r'):
            out_chars.append(ch)
            continue
        # Treat horizontal whitespace as space-like.
        is_space_like = ch in HORIZONTAL_SPACE_CODEPOINTS or unicodedata.category(ch) == 'Zs'

        is_dash_like = ch in DASH_LIKE_CODEPOINTS
        if ch == '\u2019':
            out_chars.append("'")
            replaced += 1
        elif ch == '\u201c':
            out_chars.append('"')
            replaced += 1

        elif ch == '\u201d':
            out_chars.append('"')
            replaced += 1

        elif ch == '\u2192':
            out_chars.append('->')
            replaced += 1
        elif ch == '\u2194':
            out_chars.append('<->')
            replaced += 1

        elif is_dash_like:
            out_chars.append('-')
            replaced += 1

        elif is_space_like:
            out_chars.append(' ')
            if ch != ' ':
                replaced += 1
        else:
            out_chars.append(ch)
    return (''.join(out_chars), replaced)


def iter_files(root: str, skip_hidden: bool = True) -> Iterable[str]:
    for dirpath, dirnames, filenames in os.walk(root):
        if skip_hidden:
            dirnames[:] = [d for d in dirnames if not d.startswith('.')]
        for filename in filenames:
            if skip_hidden and filename.startswith('.'):
                continue
            path = os.path.join(dirpath, filename)
            if os.path.isfile(path):
                yield path


def process_file(path: str, apply: bool, backup: bool) -> Tuple[bool, int]:
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            original = f.read()
        new_text, replaced = replace_space_like(original)
        if replaced > 0 and apply:
            if backup:
                shutil.copy2(path, path + '.bak')
            with open(path, 'w', encoding='utf-8') as f:
                f.write(new_text)
        return (replaced > 0, replaced)
    except Exception:
        return (False, 0)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Replace all space-like symbols with a regular ASCII space.')
    parser.add_argument('--input_dir', required=True, help='Root directory to process')
    parser.add_argument('--dry', action='store_true', help='Preview changes without writing files')
    parser.add_argument('--backup', action='store_true', help='Create .bak backups when applying changes')
    args = parser.parse_args(argv)

    root = os.path.abspath(args.input_dir)
    if not os.path.isdir(root):
        print(f'Directory not found: {root}', file=sys.stderr)
        return 1

    # First pass: count files for progress bar
    file_paths = list(iter_files(root))
    total_files = len(file_paths)

    if total_files == 0:
        print('No files found to process.')
        return 0

    changed_files = 0
    total_replaced = 0
    apply_changes = not args.dry

    # Process files with progress bar
    with tqdm(total=total_files, desc='Processing files', unit='file') as pbar:
        for path in file_paths:
            pbar.set_postfix({'Changed': changed_files, 'Replaced': total_replaced})
            if not is_text_file(path):
                pbar.update(1)
                continue
            changed, replaced = process_file(path, apply=apply_changes, backup=args.backup)
            if changed:
                changed_files += 1
                total_replaced += replaced
            pbar.update(1)

    mode = 'DRY-RUN' if args.dry else 'APPLY'
    print(f'\n[{mode}] Checked {total_files} files. Changed {changed_files} files. Replaced {total_replaced} chars.')
    if args.dry:
        print('Run without --dry to write changes. Use --backup to create .bak copies.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
