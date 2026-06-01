import argparse
import glob
import itertools
import json
import multiprocessing as mp
import os
from typing import Literal

import trimesh
from tqdm import tqdm
from transformers import AutoTokenizer


def value_round(number, max_decimals=6, tolerance=1e-2):
    """Round to the fewest decimal places that stays within tolerance of the original value.

    Keeps prompt numbers short without introducing meaningful geometric error.
    """

    def check_zero(num):
        # Convert "1.0" → 1 so prompts read "1" not "1.0"
        return int(num) if str(num)[-2:] == '.0' else num

    if number == 0:
        return 0

    for decimals in range(max_decimals + 1):
        rounded = round(number, decimals)
        if abs(number - rounded) < tolerance:
            return check_zero(rounded)

    return check_zero(number)


def get_model_bounds(geometry_dir, file_id):
    file_path = os.path.join(geometry_dir, file_id[:4], file_id + '.stl')
    if os.path.exists(file_path):
        mesh = trimesh.load(file_path)
        return mesh.bounds.copy()
    else:
        raise FileNotFoundError(file_path)


def preprocess_dataset(
    chunk_dir: str,
    system_message: str = 'You are CAD code generation model.',
    data_format: str = 'llama-factory',
    seq_len: int = 8192,
    splits_path: str = None,
    test_path: str = None,
    prompts_dir: str = None,
    stl_dir: str = None,
    mode: Literal['text', 'image'] = 'text',
    prepare_test: bool = False,
):
    """Convert prompt-answer file pairs in one chunk directory into JSONL records.

    Args:
        chunk_dir: Directory containing 8-char ????????.txt answer files for one chunk.
        system_message: System turn prepended to every conversation.
        data_format: 'llama-factory' (default) or 'qwen' (adds chatml format field).
        seq_len: Samples whose tokenized length exceeds this are dropped (train only).
        splits_path: JSON with a 'test' key listing DeepCAD held-out IDs; matching
            IDs are skipped unless they also appear in test_path.
        test_path: JSON with a 'test' key listing our own test split IDs.
        prompts_dir: Root of prompt files laid out as prompts_dir/<id[:4]>/<id>.txt
            (text mode) or prompts_dir/<id[:4]>/<id>.png (image mode).
        stl_dir: Root of STL files laid out as stl_dir/<id[:4]>/<id>.stl (image mode).
        mode: 'text' uses a text prompt file; 'image' derives the prompt from mesh geometry.
        prepare_test: If True, keep only test_path samples; if False, exclude them.

    Returns:
        List of JSON-serialised JSONL lines (each ending with '\\n').
    """
    # Image mode adds visual tokens on top of text tokens when checking seq_len.
    # 532/28 is the number of vision patches for a 532-px image with patch size 28.
    if mode == 'text':
        extra_input_size = 0
    elif mode == 'image':
        extra_input_size = int((532 / 28) ** 2 + 2)
    else:
        raise NotImplementedError(f'Unknown mode: {mode}')

    tokenizer = AutoTokenizer.from_pretrained('Qwen/Qwen2-VL-2B-Instruct')

    # IDs in the DeepCAD held-out split that are NOT in our own test split must be
    # excluded to avoid train/test contamination across datasets.
    deepcad_test = set()
    if splits_path is not None:
        with open(splits_path) as f:
            deepcad_test = set(json.load(f)['test'])

    test_samples = set()
    if test_path is not None:
        with open(test_path) as f:
            test_samples = set(json.load(f)['test'])

    processed_data = []
    text_files = glob.glob(os.path.join(chunk_dir, '????????.txt'))
    for text_file in text_files:
        file_id = os.path.basename(text_file).split('.')[0]

        # Skip DeepCAD test IDs that didn't make it into our test split
        if file_id in deepcad_test and file_id not in test_samples:
            continue
        # Enforce train/test separation
        if not prepare_test and test_samples and file_id in test_samples:
            continue
        if prepare_test and test_samples and file_id not in test_samples:
            continue

        prompt_file = None
        try:
            if mode == 'text':
                prompt_file = os.path.join(prompts_dir, file_id[:4], f'{file_id}.txt')
                if not os.path.exists(prompt_file):
                    print(f'Does not exist: {prompt_file}')
                    continue
                with open(prompt_file, encoding='utf-8') as f_prompt:
                    question = f_prompt.read().strip()
            elif mode == 'image':
                # Build a geometry-grounded prompt from the STL bounding box so the
                # model can relate the image to real-world scale.
                bounds = get_model_bounds(stl_dir, file_id)
                extents = abs(bounds[0] - bounds[1])
                bbox_center = (bounds[0] + bounds[1]) / 2.0
                transform_scale = str(value_round(extents.max() / 2))
                formatted_bounds = [
                    '(' + ', '.join([str(value_round(x)) for x in bounds[0]]) + ')',
                    '(' + ', '.join([str(value_round(x)) for x in bounds[1]]) + ')',
                ]
                formatted_center = '(' + ', '.join([str(value_round(x)) for x in bbox_center]) + ')'
                question = (
                    f'<image>Generate a CAD model using FeatureScript framework. '
                    f'Mesh bounds from {formatted_bounds[0]} to {formatted_bounds[1]}, '
                    f'center = {formatted_center}, scale = {transform_scale}'
                )

            with open(text_file, encoding='utf-8') as f_text:
                answer = f_text.read().strip()

            json_obj = {
                'messages': [
                    {'role': 'system', 'content': system_message},
                    {'role': 'user', 'content': question},
                    {'role': 'assistant', 'content': answer},
                ],
                'cad_file_id': file_id,
            }
            if data_format == 'qwen':
                json_obj['format'] = 'chatml'
            if mode == 'image':
                json_obj['images'] = [os.path.join(prompts_dir, file_id[:4], file_id + '.png')]

            input_data = tokenizer.apply_chat_template(
                json_obj['messages'],
                tokenize=True,
                add_generation_prompt=True,
            )
            # Drop samples that exceed the model's context window at train time;
            # keep all samples for test regardless of length.
            if not prepare_test and len(input_data) + extra_input_size > seq_len:
                continue

            processed_data.append(json.dumps(json_obj, ensure_ascii=False) + '\n')

        except Exception as e:
            print(f'Error processing {prompt_file or text_file}: {e}')

    return processed_data


def _worker(kwargs):
    return preprocess_dataset(**kwargs)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Preprocess dataset for VLM training')
    parser.add_argument('--code_dir', required=True, help='Base directory containing chunk subdirs with .txt files')
    parser.add_argument('--output_file', required=True, help='Path to the output JSONL file')
    parser.add_argument('--splits_path', help='Path to the DeepCAD train/test splits JSON')
    parser.add_argument('--test_path', help='Path to the CADFS train/test splits JSON')
    parser.add_argument('--prompts_dir', help='Directory with prompt files')
    parser.add_argument('--stl_dir', help='Directory with STL models (required only if --mode image)')
    parser.add_argument('--mode', default='text', choices=['text', 'image'], help='Processing mode')
    parser.add_argument('--data_format', default='llama-factory', choices=['llama-factory', 'qwen'])
    parser.add_argument('--seq_len', type=int, default=8192, help='Maximum sequence length for filtering')
    parser.add_argument('--prepare_test', action='store_true', help='Prepare test set instead of train set')
    parser.add_argument('--workers', type=int, default=8, help='Number of parallel workers')
    parser.add_argument('--system_message', default='You are CAD code generation model.', help='LLM System message')
    args = parser.parse_args()

    function_args = [
        {
            'chunk_dir': os.path.join(args.code_dir, chunk),
            'system_message': args.system_message,
            'data_format': args.data_format,
            'seq_len': args.seq_len,
            'splits_path': args.splits_path,
            'test_path': args.test_path,
            'prompts_dir': args.prompts_dir,
            'stl_dir': args.stl_dir,
            'mode': args.mode,
            'prepare_test': args.prepare_test,
        }
        for chunk in os.listdir(args.code_dir)
    ]

    out = []
    with mp.Pool(args.workers or mp.cpu_count()) as pool:
        for result in tqdm(pool.imap(_worker, function_args), total=len(function_args)):
            out.append(result)

    all_lines = list(itertools.chain.from_iterable(out))
    with open(args.output_file, 'w', encoding='utf-8') as f_out:
        f_out.writelines(all_lines)

    # Re-count from disk to confirm write succeeded
    count = 0
    with open(args.output_file) as f:
        for line in f:
            count += 1
    print(f'Preprocessing completed. {count} samples processed and saved to {args.output_file}')
