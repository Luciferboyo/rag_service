"""查询接口测试"""
import pytest
from test.conftest import HEADERS, make_tenant


def _create_kb(client, tenant_id: str, name: str = "QueryTestKB") -> dict:
    r = client.post("/api/kb/create", json={"tenantId": tenant_id, "name": name}, headers=HEADERS)
    assert r.status_code == 200, r.text
    return r.json()


# ── 鉴权 ──────────────────────────────────────────────────────

def test_query_requires_auth(client):
    r = client.post("/api/query", json={"tenantId": "x", "kbId": "y", "question": "test?"})
    assert r.status_code == 401


# ── 正常查询 ──────────────────────────────────────────────────

def test_query_success(client):
    tid = make_tenant()
    kb = _create_kb(client, tid)

    r = client.post(
        "/api/query",
        json={
            "tenantId": tid,
            "kbId": kb["kbId"],
            "question": "这个知识库有什么内容？",
            "mode": "hybrid",
        },
        headers=HEADERS,
    )
    assert r.status_code == 200
    data = r.json()
    assert "answer" in data
    assert data["answer"] == "测试答案"
    assert "latencyMs" in data


def test_query_with_trace_id(client):
    tid = make_tenant()
    kb = _create_kb(client, tid)

    r = client.post(
        "/api/query",
        json={
            "traceId": "trace-abc-123",
            "tenantId": tid,
            "kbId": kb["kbId"],
            "question": "测试问题",
        },
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["traceId"] == "trace-abc-123"


def test_query_all_modes(client):
    """low / high / hybrid 三种模式都应正常返回"""
    tid = make_tenant()
    kb = _create_kb(client, tid)

    for mode in ("low", "high", "hybrid"):
        r = client.post(
            "/api/query",
            json={"tenantId": tid, "kbId": kb["kbId"], "question": "test", "mode": mode},
            headers=HEADERS,
        )
        assert r.status_code == 200, f"mode={mode} failed: {r.text}"


def test_query_custom_top_k(client):
    tid = make_tenant()
    kb = _create_kb(client, tid)

    r = client.post(
        "/api/query",
        json={"tenantId": tid, "kbId": kb["kbId"], "question": "test", "topK": 10},
        headers=HEADERS,
    )
    assert r.status_code == 200


# ── 错误情况 ──────────────────────────────────────────────────

def test_query_kb_not_found(client):
    tid = make_tenant()
    r = client.post(
        "/api/query",
        json={"tenantId": tid, "kbId": "kb_nonexistent", "question": "test"},
        headers=HEADERS,
    )
    assert r.status_code == 404


def test_query_invalid_mode(client):
    tid = make_tenant()
    kb = _create_kb(client, tid)
    r = client.post(
        "/api/query",
        json={"tenantId": tid, "kbId": kb["kbId"], "question": "test", "mode": "invalid_mode"},
        headers=HEADERS,
    )
    assert r.status_code == 422


def test_query_top_k_out_of_range(client):
    tid = make_tenant()
    kb = _create_kb(client, tid)
    r = client.post(
        "/api/query",
        json={"tenantId": tid, "kbId": kb["kbId"], "question": "test", "topK": 99},
        headers=HEADERS,
    )
    assert r.status_code == 422


def test_query_missing_question(client):
    tid = make_tenant()
    kb = _create_kb(client, tid)
    r = client.post(
        "/api/query",
        json={"tenantId": tid, "kbId": kb["kbId"]},
        headers=HEADERS,
    )
    assert r.status_code == 422


def test_query_missing_kb_id(client):
    """kbId 现在是必填字段，不传应返回 422"""
    tid = make_tenant()
    r = client.post(
        "/api/query",
        json={"tenantId": tid, "question": "test"},
        headers=HEADERS,
    )
    assert r.status_code == 422


# ── 请求级别覆盖查询模型 ──────────────────────────────────────

def test_query_with_custom_model(client):
    """携带 queryModel 字段时应正常通过（rag_manager.query 已 mock）"""
    tid = make_tenant()
    kb = _create_kb(client, tid)

    r = client.post(
        "/api/query",
        json={
            "tenantId": tid,
            "kbId": kb["kbId"],
            "question": "自定义模型查询",
            "queryModel": {
                "baseUrl": "https://api.openai.com/v1",
                "apiKey": "sk-test",
                "model": "gpt-4o",
            },
        },
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["answer"] == "测试答案"
