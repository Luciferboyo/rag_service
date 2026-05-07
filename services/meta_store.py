"""
KB 元数据持久化
每个 tenant 在 {STORAGE_DIR}/{tenantId}/meta.json 存一个文件
"""
import json
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from core.config import settings

# 每个 tenantId 一把写锁，防止并发写坏文件
_locks: dict[str, asyncio.Lock] = {}


def _meta_path(tenant_id: str) -> Path:
    path = Path(settings.storage_dir) / tenant_id
    path.mkdir(parents=True, exist_ok=True)
    return path / "meta.json"


def _load(tenant_id: str) -> dict:
    p = _meta_path(tenant_id)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(tenant_id: str, data: dict):
    _meta_path(tenant_id).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _lock(tenant_id: str) -> asyncio.Lock:
    if tenant_id not in _locks:
        _locks[tenant_id] = asyncio.Lock()
    return _locks[tenant_id]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── 公开接口 ──────────────────────────────────────────────────

async def create_kb(
    tenant_id: str,
    kb_id: str,
    name: str,
    description: str | None,
    model_config: dict | None = None,
):
    async with _lock(tenant_id):
        data = _load(tenant_id)
        data[kb_id] = {
            "kbId": kb_id,
            "name": name,
            "description": description,
            "createdAt": _now(),
            "modelConfig": model_config,
            "docs": [],
        }
        _save(tenant_id, data)


def get_kb_model_config(tenant_id: str, kb_id: str) -> dict | None:
    data = _load(tenant_id)
    return data.get(kb_id, {}).get("modelConfig")


async def add_doc(
    tenant_id: str,
    kb_id: str,
    doc_id: str,
    file_name: str,
    chunk_count: int,
    rag_doc_ids: list[str],
    status: str = "indexing",
):
    async with _lock(tenant_id):
        data = _load(tenant_id)
        if kb_id not in data:
            return
        data[kb_id]["docs"].append({
            "docId": doc_id,
            "fileName": file_name,
            "chunkCount": chunk_count,
            "uploadedAt": _now(),
            "ragDocIds": rag_doc_ids,
            "status": status,
        })
        _save(tenant_id, data)


async def update_doc_status(
    tenant_id: str,
    kb_id: str,
    doc_id: str,
    status: str,
    error: str | None = None,
):
    async with _lock(tenant_id):
        data = _load(tenant_id)
        if kb_id not in data:
            return
        for doc in data[kb_id]["docs"]:
            if doc["docId"] == doc_id:
                doc["status"] = status
                if error is not None:
                    doc["error"] = error
                break
        _save(tenant_id, data)


def get_doc(tenant_id: str, kb_id: str, doc_id: str) -> dict | None:
    data = _load(tenant_id)
    for doc in data.get(kb_id, {}).get("docs", []):
        if doc["docId"] == doc_id:
            return doc
    return None


async def delete_doc(tenant_id: str, kb_id: str, doc_id: str):
    async with _lock(tenant_id):
        data = _load(tenant_id)
        if kb_id not in data:
            return
        data[kb_id]["docs"] = [
            d for d in data[kb_id]["docs"] if d["docId"] != doc_id
        ]
        _save(tenant_id, data)


async def update_kb(
    tenant_id: str,
    kb_id: str,
    name: str | None = None,
    description: str | None = None,
):
    async with _lock(tenant_id):
        data = _load(tenant_id)
        if kb_id not in data:
            return
        if name is not None:
            data[kb_id]["name"] = name
        if description is not None:
            data[kb_id]["description"] = description
        _save(tenant_id, data)


async def delete_kb(tenant_id: str, kb_id: str):
    async with _lock(tenant_id):
        data = _load(tenant_id)
        data.pop(kb_id, None)
        _save(tenant_id, data)


def kb_exists(tenant_id: str, kb_id: str) -> bool:
    return kb_id in _load(tenant_id)


def get_kb(tenant_id: str, kb_id: str) -> dict | None:
    return _load(tenant_id).get(kb_id)


def list_kbs(tenant_id: str) -> list[dict]:
    data = _load(tenant_id)
    return list(data.values())


def list_docs(tenant_id: str, kb_id: str) -> list[dict]:
    data = _load(tenant_id)
    return data.get(kb_id, {}).get("docs", [])
