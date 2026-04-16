import os
import logging
import numpy as np
from typing import Optional
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.utils import EmbeddingFunc, TokenTracker
from models.schemas import ModelConfig
from core.config import settings

logger = logging.getLogger("rag.token")


def make_llm_func(cfg: ModelConfig):
    """
    根据用户配置动态生成 LLM 调用函数。
    兼容 OpenRouter / OpenAI / DeepSeek / Ollama 等任意 OpenAI 兼容接口。
    """
    async def llm_func(prompt, system_prompt=None, history_messages=[], **kwargs):
        tracker = TokenTracker()
        result = await openai_complete_if_cache(
            model=cfg.model,
            prompt=prompt,
            system_prompt=system_prompt,
            history_messages=history_messages,
            api_key=cfg.apiKey,
            base_url=cfg.baseUrl,
            token_tracker=tracker,
            **kwargs,
        )
        usage = tracker.get_usage()
        logger.info(
            "[LLM] model=%s | prompt_tokens=%d | completion_tokens=%d | total_tokens=%d",
            cfg.model,
            usage["prompt_tokens"],
            usage["completion_tokens"],
            usage["total_tokens"],
        )
        return result
    return llm_func

def make_embedding_func(cfg: ModelConfig, dim: int) -> EmbeddingFunc:
    """根据用户配置动态生成 Embedding 函数。"""
    async def embed_func(texts: list[str]) -> np.ndarray:
        return await openai_embed(
            texts,
            model=cfg.model,
            api_key=cfg.apiKey,
            base_url=cfg.baseUrl,
        )

    return EmbeddingFunc(
        embedding_dim=dim,
        max_token_size=8192,
        func=embed_func,
    )

def get_default_index_config() -> ModelConfig:
    return ModelConfig(
        baseUrl=settings.default_index_base_url,
        apiKey=settings.default_index_api_key,
        model=settings.default_index_model,
    )

def get_default_query_config() -> ModelConfig:
    return ModelConfig(
        baseUrl=settings.default_query_base_url,
        apiKey=settings.default_query_api_key,
        model=settings.default_query_model,
    )

def get_default_embedding_config() -> tuple[ModelConfig, int]:
    return (
        ModelConfig(
            baseUrl=settings.default_embedding_base_url,
            apiKey=settings.default_embedding_api_key,
            model=settings.default_embedding_model,
        ),
        settings.default_embedding_dim,
    )


