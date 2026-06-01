import logging
import pathlib
from typing import List

logger = logging.getLogger(__name__)

_DATA_DIR = pathlib.Path(__file__).resolve().parent / 'data'


def compose_few_shot_examples() -> str:
    """Build few-shot examples by reading code-annotation pairs from the data directory.

    Looks for FeatureScript code under data/few-shots/FS/ and annotations under
    data/few-shots/annotations/.
    """
    try:
        codes_dir = _DATA_DIR / 'few-shots' / 'FS'
        outputs_dir = _DATA_DIR / 'few-shots' / 'annotations'

        if not codes_dir.exists() or not outputs_dir.exists():
            return ''

        examples: List[str] = []

        for code_path in sorted(codes_dir.glob('*.txt')):
            stem = code_path.stem
            anno_path = None
            for candidate in sorted(outputs_dir.glob(f'{stem}.txt')):
                anno_path = candidate
                break
            if anno_path is None:
                continue

            try:
                code_text = code_path.read_text(encoding='utf-8').strip()
                anno_text = anno_path.read_text(encoding='utf-8').strip()
            except Exception:
                continue

            example_text = (
                f'Example {len(examples) + 1} – {stem}\n\n'
                'FeatureScript code:\n' + code_text + '\n\n' + 'Annotation:\n' + anno_text
            )
            examples.append(example_text)

        return '\n\n'.join(examples)
    except Exception:
        return ''
