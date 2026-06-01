import argparse
import json
import logging
import os
from pathlib import Path
from typing import List, Tuple, Union

import torch
from qwen_vl_utils import process_vision_info
from tqdm import tqdm
from transformers import AutoProcessor
from vllm import LLM, SamplingParams

os.environ.setdefault('VLLM_WORKER_MULTIPROC_METHOD', 'spawn')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

MAX_TOKENS = 8192
SYSTEM_PROMPT = 'You are CAD code generation model.'


def load_text_data(split) -> List[Tuple[str, str]]:
    with open(split) as f:
        data = [json.loads(line) for line in f]
    prompts = [(line['cad_file_id'], line['messages'][1]['content']) for line in data]
    logger.info(f'Loaded {len(prompts)} samples')
    logger.info(f'Sample: {prompts[0]}')
    return prompts


def load_image_text_data(split) -> List[Tuple[str, str, str]]:
    with open(split) as f:
        data = [json.loads(line) for line in f]
    samples = []
    for line in data:
        sample = line['cad_file_id']
        prompt = line['messages'][1]['content']
        image_path = line['images'][0]
        if not Path(image_path).exists():
            raise RuntimeError(f'Image not found: {image_path}')
        samples.append((sample, prompt, image_path))
    logger.info(f'Loaded {len(samples)} samples')
    logger.info(f'Sample: {samples[0]}')
    return samples


class Processor:
    def __init__(self, model_path: str, tensor_parallel_size: int = 1, dtype=torch.bfloat16):
        self.processor = AutoProcessor.from_pretrained(model_path, trust_remote_code=True)
        self.llm = LLM(
            model=model_path,
            max_model_len=MAX_TOKENS,
            tensor_parallel_size=tensor_parallel_size,
            dtype=dtype,
        )
        self.sampling_params = SamplingParams(
            temperature=0.01,
            top_p=0.001,
            top_k=1,
            max_tokens=MAX_TOKENS,
        )

    def tokenize(self, prompts_with_images: List) -> List:
        """Format prompts using Qwen's chat template."""
        tokenized = []
        for prompt_data in tqdm(prompts_with_images, desc='Tokenizing'):
            if isinstance(prompt_data, tuple):
                text, image_path = prompt_data
            else:
                text, image_path = prompt_data, None
            text = text.replace('<image>', '')
            if image_path:
                content = [
                    {'type': 'image', 'image': image_path},
                    {'type': 'text', 'text': text},
                ]
                messages = [
                    {'role': 'system', 'content': SYSTEM_PROMPT},
                    {'role': 'user', 'content': content},
                ]
                prompt = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
                image_inputs, _ = process_vision_info(messages)
                formatted_prompt = {'prompt': prompt, 'multi_modal_data': {'image': image_inputs}}
            else:
                formatted_prompt = self.processor.apply_chat_template(
                    [
                        {'role': 'system', 'content': SYSTEM_PROMPT},
                        {'role': 'user', 'content': text},
                    ],
                    tokenize=False,
                    add_generation_prompt=True,
                )
            tokenized.append(formatted_prompt)
        logger.info(f'Tokenized {len(tokenized)} samples')
        logger.info(f'Tokenized sample: {tokenized[0]}')
        return tokenized

    def process_dataset(self, prompts: List, output_dir: Union[str, Path]) -> None:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        text_image_pairs = [(p[1], p[2]) if len(p) > 2 else p[1] for p in prompts]
        outputs = self.llm.generate(self.tokenize(text_image_pairs), self.sampling_params)
        for item, output in zip(prompts, outputs):
            (output_dir / f'{item[0]}.txt').write_text(output.outputs[0].text)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-m', '--mode', type=str, default='text', help='Input mode: "text" or "image"')
    parser.add_argument('-c', '--checkpoint', type=str, required=True, help='Model checkpoint path or HF repo ID')
    parser.add_argument('-o', '--output_dir', type=str, required=True, help='Directory to save generated .txt files')
    parser.add_argument('-s', '--split', type=str, required=True, help='JSONL file with samples for inference')
    args = parser.parse_args()

    tensor_parallel_size = torch.cuda.device_count() or 1

    if args.mode == 'text':
        prompts = load_text_data(args.split)
        dtype = torch.bfloat16
    elif args.mode == 'image':
        prompts = load_image_text_data(args.split)
        dtype = torch.float32
        os.environ['VLLM_ATTENTION_BACKEND'] = 'XFORMERS'
    else:
        raise NotImplementedError(f'Unknown mode: {args.mode}')

    processor = Processor(args.checkpoint, tensor_parallel_size=tensor_parallel_size, dtype=dtype)
    processor.process_dataset(prompts=prompts, output_dir=args.output_dir)
