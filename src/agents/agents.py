import logging
import os

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings
from pydantic_ai.providers.openai import OpenAIProvider

from src.annotations.prompts import compose_generator_system_prompt, compose_reviewer_system_prompt
from src.annotations.utils import load_fs_docs

logger = logging.getLogger(__name__)


def build_model() -> OpenAIChatModel:
    """Build an OpenAIChatModel using env vars.

    Env vars:
    - OPENAI_API_KEY
    - OPENAI_BASE_URL (default 'https://openrouter.ai/api/v1')
    - OPENAI_MODEL (default 'google/gemini-2.5-flash-lite')
    """
    api_key = os.getenv('OPENAI_API_KEY')
    base_url = os.getenv('OPENAI_BASE_URL')
    model_id = os.getenv('OPENAI_MODEL')

    provider = OpenAIProvider(api_key=api_key, base_url=base_url)

    settings = OpenAIChatModelSettings(
        temperature=1,
        openai_reasoning_effort='medium',
        top_p=1,
    )
    model = OpenAIChatModel(model_id, provider=provider, settings=settings)
    logger.info(f'Initialized OpenAIChatModel: {model_id} (base_url={base_url})')
    return model


def create_generator_agent(model) -> Agent:
    docs_text = load_fs_docs()
    return Agent(
        instructions=compose_generator_system_prompt(docs_text),
        model=model,
        retries=3,
        output_retries=3,
    )


def create_reviewer_agent(model) -> Agent:
    docs_text = load_fs_docs()
    return Agent(
        instructions=compose_reviewer_system_prompt(docs_text),
        model=model,
        retries=3,
        output_retries=3,
    )
