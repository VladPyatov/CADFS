import asyncio
import logging
import os
import pathlib
from json.decoder import JSONDecodeError
from typing import List

from openai import APIConnectionError, APIError, APIStatusError, APITimeoutError, RateLimitError
from pydantic import ValidationError as PydanticValidationError
from pydantic_ai import Agent

try:
    from pydantic_core import ValidationError as PydanticCoreValidationError
except Exception:

    class PydanticCoreValidationError(Exception):  # type: ignore[no-redef]
        pass


from pydantic_ai.exceptions import UnexpectedModelBehavior
from tqdm.asyncio import tqdm

from src.agents.agents import build_model
from src.annotations.prompts import (
    compose_generator_system_prompt,
    compose_generator_user_prompt,
    compose_reviewer_system_prompt,
    compose_reviewer_user_prompt,
)
from src.annotations.utils import (
    filter_fsdocs_by_operations,
    list_featurescript_rel_paths,
    load_fs_docs,
    logfire_span,
    parse_operations_from_prompt,
    setup_logfire,
)

logger = logging.getLogger(__name__)

_RETRYABLE_ERRORS = (
    JSONDecodeError,
    ConnectionError,
    TimeoutError,
    APITimeoutError,
    APIConnectionError,
    APIStatusError,
    RateLimitError,
    APIError,
    PydanticValidationError,
    PydanticCoreValidationError,
    UnexpectedModelBehavior,
)


async def _retry_with_backoff(coro_factory, max_retries: int, label: str):
    """Generic retry wrapper with exponential backoff for LLM calls."""
    for attempt in range(max_retries):
        try:
            return await coro_factory()
        except _RETRYABLE_ERRORS as e:
            if attempt == max_retries - 1:
                logger.error(f'Failed after {max_retries} attempts with error: {e}')
                raise

            if isinstance(e, RateLimitError):
                wait_time = min(60, (2 ** (attempt + 2)))
                logger.warning(f'[{label}] Rate limit hit on attempt {attempt + 1}, retrying in {wait_time} seconds...')
            elif isinstance(e, APIError) and hasattr(e, 'response') and e.response.status_code == 400:
                wait_time = min(5, (1 + attempt * 0.5))
                logger.warning(
                    f'[{label}] 400 Bad Request on attempt {attempt + 1}, retrying in {wait_time:.1f} seconds...'
                )
            else:
                wait_time = (2**attempt) + (attempt * 0.1)
                logger.warning(
                    f'[{label}] Attempt {attempt + 1} failed with {type(e).__name__}, retrying in {wait_time:.1f} seconds...'
                )

            await asyncio.sleep(wait_time)


# ---------------------------------------------------------------------------
# Single-file generation / review
# ---------------------------------------------------------------------------


async def a_generate_annotation(generator: Agent, code_text: str) -> str:
    prompt = compose_generator_user_prompt(code_text=code_text)

    async def _call():
        result = await generator.run(prompt)
        return result.output

    return await _retry_with_backoff(_call, max_retries=3, label='generate')


def generate_annotation(generator: Agent, code_text: str) -> str:
    return asyncio.run(a_generate_annotation(generator, code_text))


async def a_review_annotation(reviewer: Agent, code_text: str, draft: str) -> str:
    prompt = compose_reviewer_user_prompt(code_text=code_text, draft_text=draft)

    async def _call():
        result = await reviewer.run(prompt)
        return result.output

    return await _retry_with_backoff(_call, max_retries=5, label='review')


def review_annotation(reviewer: Agent, code_text: str, draft: str) -> str:
    return asyncio.run(a_review_annotation(reviewer, code_text, draft))


# ---------------------------------------------------------------------------
# Batch processing
# ---------------------------------------------------------------------------


def process_folder(
    input_dir: pathlib.Path,
    output_dir: pathlib.Path,
    enable_logfire: bool = False,
) -> List[pathlib.Path]:
    return asyncio.run(a_process_folder(input_dir=input_dir, output_dir=output_dir, enable_logfire=enable_logfire))


async def a_process_folder(
    input_dir: pathlib.Path,
    output_dir: pathlib.Path,
    enable_logfire: bool = False,
) -> List[pathlib.Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    setup_logfire(enable_logfire)
    model = build_model()

    max_concurrency = int(os.getenv('ANNO_MAX_CONCURRENCY', '200'))
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _process_one(rel_path: str, generator_only: bool = False) -> pathlib.Path:
        async with semaphore:
            rel_path_obj = pathlib.Path(rel_path)
            prompt_rel = rel_path_obj.with_suffix('').as_posix() + '.prompt.txt'
            prompt_path = input_dir / prompt_rel
            docs_full = load_fs_docs()

            if prompt_path.exists():
                prompt_text = prompt_path.read_text(encoding='utf-8')
                ops = parse_operations_from_prompt(prompt_text)
                docs_filtered = filter_fsdocs_by_operations(docs_full, ops)
            else:
                docs_filtered = docs_full

            generator = Agent(
                instructions=compose_generator_system_prompt(docs_filtered),
                model=model,
                retries=3,
                output_retries=3,
            )
            reviewer = (
                Agent(
                    instructions=compose_reviewer_system_prompt(docs_filtered),
                    model=model,
                    retries=3,
                    output_retries=3,
                )
                if not generator_only
                else None
            )

            with logfire_span(f'agent:{rel_path}'):
                code_text = (input_dir / rel_path).read_text(encoding='utf-8')
                draft = await a_generate_annotation(generator, code_text=code_text)

            if not generator_only and reviewer is not None:
                with logfire_span(f'reviewer:{rel_path}'):
                    final_text = await a_review_annotation(reviewer, code_text=code_text, draft=draft)
            else:
                final_text = draft

            stem = rel_path_obj.stem
            out_rel_path = rel_path_obj.parent / f'{stem}.txt'
            out_path = output_dir / out_rel_path
            out_path.parent.mkdir(parents=True, exist_ok=True)

            result_text = final_text.strip() + '\n'
            out_path.write_text(result_text, encoding='utf-8')
            return out_path

    logger.info('Scanning input directory for FeatureScript files...')
    files_to_process = list_featurescript_rel_paths(input_dir)
    total_files = len(files_to_process)

    logger.info(f'Starting processing of {total_files} files with concurrency={max_concurrency}...')

    queue: asyncio.Queue[str | None] = asyncio.Queue()
    for rel_path in files_to_process:
        queue.put_nowait(rel_path)
    for _ in range(max_concurrency):
        queue.put_nowait(None)

    results: List[pathlib.Path] = []
    errors: List[str] = []

    async def _worker(worker_idx: int) -> None:
        while True:
            rel_path = await queue.get()
            if rel_path is None:
                break
            try:
                out_path = await _process_one(rel_path, generator_only=False)
                results.append(out_path)
            except Exception as e:
                errors.append(str(e))
                logger.error(f'Worker {worker_idx} error: {e}')
            finally:
                queue.task_done()

    workers = [asyncio.create_task(_worker(i)) for i in range(min(max_concurrency, max(1, total_files)))]

    with tqdm(total=total_files, desc='Processing files', unit='file') as pbar:
        processed_prev = 0
        while any(not w.done() for w in workers):
            await asyncio.sleep(0.2)
            processed_now = len(results) + len(errors)
            delta = processed_now - processed_prev
            if delta > 0:
                pbar.update(delta)
                pbar.set_postfix(
                    {
                        'processed': len(results),
                        'errors': len(errors),
                        'remaining': total_files - processed_now,
                    }
                )
                processed_prev = processed_now

    await asyncio.gather(*workers, return_exceptions=True)

    logger.info(f'Processing completed. Processed {len(results)} files, errors: {len(errors)}')
    if errors:
        logger.warning(f'Processing errors: {errors[:5]}...')
    return results
