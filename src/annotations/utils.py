import logging
import os
import pathlib
import re
from contextlib import nullcontext
from typing import Dict, List

import logfire

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Logfire integration
# ---------------------------------------------------------------------------

LOGFIRE_ENABLED = False


def setup_logfire(enable: bool) -> None:
    """Configure Logfire once per run if enabled and token present."""
    global LOGFIRE_ENABLED
    token = os.getenv('LOGFIRE_TOKEN')
    LOGFIRE_ENABLED = bool(enable and token)
    if LOGFIRE_ENABLED:
        logfire.configure(token=token)
        logfire.instrument_pydantic_ai()
        logger.info('Logfire enabled')
    else:
        logger.info('Logfire disabled')


def logfire_span(name: str):
    """Return a Logfire span ctx if enabled, otherwise a no-op context manager."""
    return logfire.span(name) if LOGFIRE_ENABLED else nullcontext()


# ---------------------------------------------------------------------------
# FeatureScript docs loading & filtering
# ---------------------------------------------------------------------------

_DATA_DIR = pathlib.Path(__file__).resolve().parent / 'data'


def load_fs_docs() -> str:
    fsdocs_path = _DATA_DIR / 'fsdocs.md'
    if not fsdocs_path.exists():
        return ''
    return fsdocs_path.read_text(encoding='utf-8')


def split_fsdocs_sections(docs_text: str) -> List[Dict[str, str]]:
    """Split fsdocs.md into sections keyed by their '## ' headings.

    Returns a list of {"heading": str, "content": str} preserving order.
    """
    sections: List[Dict[str, str]] = []
    current_heading: str | None = None
    current_lines: List[str] = []

    for line in docs_text.splitlines():
        if line.startswith('## '):
            if current_heading is not None:
                sections.append(
                    {
                        'heading': current_heading,
                        'content': '\n'.join(current_lines).rstrip() + '\n',
                    }
                )
            current_heading = line[3:].strip()
            current_lines = []
        else:
            if current_heading is not None:
                current_lines.append(line)

    if current_heading is not None:
        sections.append(
            {
                'heading': current_heading,
                'content': '\n'.join(current_lines).rstrip() + '\n',
            }
        )

    return sections


def parse_operations_from_prompt(prompt_text: str) -> List[str]:
    """Extract operation keywords from a *.prompt.txt description."""
    text = prompt_text.lower()
    ops = []
    candidates = [
        'sketch',
        'extrude',
        'chamfer',
        'fillet',
        'shell',
        'cplane',
        'loft',
        'revolve',
        'sweep',
        'mirror',
        'hole',
        'circularpattern',
        'booleanBodies',
        'deleteBodies',
        'transform',
        'assignVariable',
        'createPoint',
    ]
    for token in candidates:
        if token in text:
            ops.append(token)
    return ops


def filter_fsdocs_by_operations(docs_text: str, operations: List[str]) -> str:
    """Filter fsdocs to include only sections relevant to the given operations."""
    ops_set = {op.lower() for op in operations}

    op_to_keywords: Dict[str, List[str]] = {
        'sketch': [
            'newSketch',
            'skLineSegment',
            'skCircle',
            'skArc',
            'skEllipse',
            'skEllipticalArc',
            'skPoint',
            'skText',
            'skSolve',
            'skSetInitialGuess',
            'sketchEntityQuery',
        ],
        'extrude': ['extrude'],
        'chamfer': ['chamfer'],
        'fillet': ['fillet'],
        'shell': ['shell'],
        'cplane': ['cPlane'],
        'loft': ['loft'],
        'revolve': ['revolve'],
        'sweep': ['sweep'],
        'mirror': ['mirror'],
        'hole': ['hole'],
        'circularpattern': ['circularPattern'],
        'booleanbodies': ['booleanBodies'],
        'deletebodies': ['deleteBodies'],
        'transform': ['transform'],
        'assignvariable': ['assignVariable'],
        'createpoint': ['createPoint'],
    }

    helper_keywords: List[str] = []
    if 'sketch' in ops_set or 'extrude' in ops_set:
        helper_keywords.extend(
            [
                'qSketchRegion',
                'qCreatedBy',
                'makeQuery',
                'topologyDisambiguation',
                'orderDisambiguation',
                'originalSetDisambiguation',
                'qUnion',
                'sketchEntityQuery',
            ]
        )

    wanted_keywords: List[str] = []
    for op in ops_set:
        wanted_keywords.extend(op_to_keywords.get(op, []))
    wanted_keywords.extend(helper_keywords)

    if not wanted_keywords:
        return docs_text

    sections = split_fsdocs_sections(docs_text)
    selected_parts: List[str] = []
    for sec in sections:
        heading = sec['heading']
        for kw in wanted_keywords:
            if kw.lower() in heading.lower():
                selected_parts.append(f'## {heading}\n{sec["content"]}\n')
                break

    if not selected_parts:
        return docs_text
    return '\n'.join(selected_parts).strip() + '\n'


# ---------------------------------------------------------------------------
# File IO helpers
# ---------------------------------------------------------------------------


def read_featurescript_files(input_dir: pathlib.Path) -> Dict[str, str]:
    contents: Dict[str, str] = {}
    for path in sorted(input_dir.rglob('*.txt')):
        if re.match(r'^\d{8}\.txt$', path.name):
            rel_path = path.relative_to(input_dir)
            contents[str(rel_path)] = path.read_text(encoding='utf-8')
    return contents


def list_featurescript_rel_paths(input_dir: pathlib.Path) -> List[str]:
    rel_paths: List[str] = []
    for path in sorted(input_dir.rglob('*.txt')):
        if re.match(r'^\d{8}\.txt$', path.name):
            rel_paths.append(str(path.relative_to(input_dir)))
    return rel_paths


def sanitize_for_filename(token: str) -> str:
    """Sanitize arbitrary text for safe use in filenames."""
    return re.sub(r'[^A-Za-z0-9_.-]+', '-', token).strip('-._') or 'model'
