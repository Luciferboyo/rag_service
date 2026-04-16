import asyncio
from pathlib import Path
from lightrag import LightRAG, QueryParam
from lightrag.kg.shared_storage import initialize_pipeline_status
from models.schemas import ModelConfig, RagModelConfig
from services.model_factory import (
    make_llm_func, make_embedding_func,
    get_default_index_config, get_default_embedding_config,
)
from core.config import settings

# key = "tenantId:kbId"
_instances: dict[str, LightRAG] = {}
_init_locks: dict[str, asyncio.Lock] = {}


def _working_dir(tenant_id: str, kb_id: str) -> str:
    path = Path(settings.storage_dir) / tenant_id / kb_id
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


async def get_or_create(
    tenant_id: str,
    kb_id: str,
    model_cfg: RagModelConfig | None = None,
) -> LightRAG:
    """
    获取或创建 LightRAG 实例。
    每个 (tenantId, kbId) 对应一个独立实例，完全隔离。
    model_cfg 优先使用，没有则用环境变量默认值。
    """
    key = f"{tenant_id}:{kb_id}"

    if key not in _init_locks:
        _init_locks[key] = asyncio.Lock()

    async with _init_locks[key]:
        if key not in _instances:
            index_cfg = (model_cfg and model_cfg.index) or get_default_index_config()
            emb_cfg, emb_dim = get_default_embedding_config()
            if model_cfg and model_cfg.embedding:
                emb_cfg = model_cfg.embedding
                # embedding dim 根据模型自动判断（常见的）
                emb_dim = _guess_dim(emb_cfg.model)

            rag = LightRAG(
                working_dir=_working_dir(tenant_id, kb_id),
                llm_model_func=make_llm_func(index_cfg),
                embedding_func=make_embedding_func(emb_cfg, emb_dim),
                # 分块参数（在 rag_manager 层控制，chunker.py 在上层分好再传入）
                chunk_token_size=512,
                chunk_overlap_token_size=50,
                # 相似度阈值：低于此值的检索结果会被丢弃（默认0.2）
                vector_db_storage_cls_kwargs={"cosine_better_than_threshold": settings.cosine_threshold},
            )
            await rag.initialize_storages()
            await initialize_pipeline_status()
            _instances[key] = rag

    return _instances[key]


async def insert_chunks(
    tenant_id: str,
    kb_id: str,
    chunks: list[str],
    model_cfg: RagModelConfig | None = None,
) -> int:
    """将已分好的 chunks 插入知识图谱。返回 chunk 数量。"""
    rag = await get_or_create(tenant_id, kb_id, model_cfg)
    # LightRAG ainsert 支持传 list，每个元素独立建图
    await rag.ainsert(chunks)
    return len(chunks)


async def query(
    tenant_id: str,
    kb_id: str,
    question: str,
    mode: str = "hybrid",
    top_k: int = 5,
    query_model_cfg: ModelConfig | None = None,
) -> dict:
    """查询知识图谱，query_model_cfg 可在请求级别切换回答模型。"""
    rag = await get_or_create(tenant_id, kb_id)

    # 临时构造独立的 llm_func，不污染共享实例
    param = QueryParam(mode=mode, top_k=top_k)
    if query_model_cfg:
        param.model_func = make_llm_func(query_model_cfg)

    answer = await rag.aquery(question, param=param)
    return {"answer": answer, "sources": [], "entities": []}


async def delete_kb(tenant_id: str, kb_id: str):
    import shutil
    key = f"{tenant_id}:{kb_id}"
    rag = _instances.pop(key, None)
    _init_locks.pop(key, None)   # 同时清理 lock，避免内存泄漏
    if rag and hasattr(rag, "finalize_storages"):
        await rag.finalize_storages()
    working_dir = Path(settings.storage_dir) / tenant_id / kb_id
    if working_dir.exists():
        shutil.rmtree(working_dir)


def _guess_dim(model: str) -> int:
    """根据模型名猜测 embedding 维度。"""
    if "3-large" in model:
        return 3072
    if "3-small" in model or "ada-002" in model:
        return 1536
    if "nomic" in model:
        return 768
    if "jina" in model:
        return 1024
    return 1536  # 默认