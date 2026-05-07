"""
全局测试配置
- 设置临时目录作为 STORAGE_DIR，避免污染真实数据
- 自动 mock 掉 LightRAG（rag_manager），无需真实 LLM/向量库
- 提供 client 和 make_tenant 工具
"""
import os
import uuid
import tempfile

# ── 必须在导入 main / services 之前设置环境变量 ──────────────────
_DATA_DIR = tempfile.mkdtemp(prefix="rag_test_")
os.environ.setdefault("STORAGE_DIR", _DATA_DIR)
os.environ.setdefault("INTERNAL_SECRET", "test-secret")
os.environ.setdefault("DEFAULT_INDEX_API_KEY", "test-key")
os.environ.setdefault("DEFAULT_QUERY_API_KEY", "test-key")
os.environ.setdefault("DEFAULT_EMBEDDING_API_KEY", "test-key")

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

# 所有测试共用的请求头
HEADERS = {"Authorization": "Bearer test-secret"}


def make_tenant() -> str:
    """每次返回唯一 tenantId，防止用例间数据污染"""
    return f"t_{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def mock_rag():
    """
    全局自动 mock rag_manager 的所有对外函数。
    TestClient 会在 post/put 返回前执行 BackgroundTask，
    所以 insert_chunks mock 会立即触发并将状态改为 indexed。
    """
    with (
        patch("services.rag_manager.get_or_create", new_callable=AsyncMock),
        patch(
            "services.rag_manager.insert_chunks",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "services.rag_manager.query",
            new_callable=AsyncMock,
            return_value={"answer": "测试答案", "sources": [], "entities": []},
        ),
        patch("services.rag_manager.delete_document", new_callable=AsyncMock),
        patch("services.rag_manager.delete_kb", new_callable=AsyncMock),
    ):
        yield


@pytest.fixture
def client():
    """返回 FastAPI TestClient，每个用例独立创建"""
    from main import app
    with TestClient(app) as c:
        yield c
