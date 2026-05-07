"""文档上传、状态查询、删除接口测试"""
import io
import pytest
from unittest.mock import patch
from test.conftest import HEADERS, make_tenant

# ── 测试用文本内容（满足最少 20 字要求）────────────────────────
SAMPLE_TXT = b"This is a sample document with enough content for testing purposes. " * 5
SAMPLE_MD  = b"# Test\n\nThis is a markdown document with enough content to pass validation. " * 3


def _upload(client, kb_id: str, tenant_id: str, filename: str, content: bytes, expected_status: int = 200):
    r = client.post(
        f"/api/kb/{kb_id}/upload",
        data={"tenantId": tenant_id},
        files={"files": (filename, io.BytesIO(content), "text/plain")},
        headers=HEADERS,
    )
    assert r.status_code == expected_status, r.text
    return r.json()


def _create_kb(client, tenant_id: str, name: str = "TestKB") -> dict:
    r = client.post("/api/kb/create", json={"tenantId": tenant_id, "name": name}, headers=HEADERS)
    assert r.status_code == 200, r.text
    return r.json()


# ── 上传成功 ──────────────────────────────────────────────────

def test_upload_txt(client):
    tid = make_tenant()
    kb = _create_kb(client, tid)
    result = _upload(client, kb["kbId"], tid, "test.txt", SAMPLE_TXT)
    assert isinstance(result, list)
    assert len(result) == 1
    doc = result[0]
    assert doc["docId"].startswith("doc_")
    assert doc["fileName"] == "test.txt"
    assert doc["chunkCount"] >= 1
    # BackgroundTask 在 TestClient 内同步执行，状态应变为 indexed
    assert doc["status"] in ("indexing", "indexed")


def test_upload_md(client):
    tid = make_tenant()
    kb = _create_kb(client, tid)
    result = _upload(client, kb["kbId"], tid, "readme.md", SAMPLE_MD)
    assert result[0]["fileName"] == "readme.md"


def test_upload_multiple_files(client):
    tid = make_tenant()
    kb = _create_kb(client, tid)
    r = client.post(
        f"/api/kb/{kb['kbId']}/upload",
        data={"tenantId": tid},
        files=[
            ("files", ("a.txt", io.BytesIO(SAMPLE_TXT), "text/plain")),
            ("files", ("b.txt", io.BytesIO(SAMPLE_TXT + b"extra"), "text/plain")),
        ],
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert len(r.json()) == 2


# ── 上传后状态查询 ────────────────────────────────────────────

def test_doc_status_indexed(client):
    """上传后通过 status 接口查询，状态应为 indexed（TestClient 同步执行 background task）"""
    tid = make_tenant()
    kb = _create_kb(client, tid)
    docs = _upload(client, kb["kbId"], tid, "status_test.txt", SAMPLE_TXT)
    doc_id = docs[0]["docId"]

    r = client.get(
        f"/api/kb/{kb['kbId']}/docs/{doc_id}/status?tenantId={tid}",
        headers=HEADERS,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["docId"] == doc_id
    assert data["status"] == "indexed"


def test_doc_status_not_found(client):
    tid = make_tenant()
    kb = _create_kb(client, tid)
    r = client.get(
        f"/api/kb/{kb['kbId']}/docs/doc_nonexistent/status?tenantId={tid}",
        headers=HEADERS,
    )
    assert r.status_code == 404


def test_doc_status_kb_not_found(client):
    tid = make_tenant()
    r = client.get(
        f"/api/kb/kb_nonexistent/docs/doc_xxx/status?tenantId={tid}",
        headers=HEADERS,
    )
    assert r.status_code == 404


# ── 重复文档防护 ──────────────────────────────────────────────

def test_duplicate_upload_returns_409(client):
    tid = make_tenant()
    kb = _create_kb(client, tid)
    kb_id = kb["kbId"]

    # 第一次上传成功
    _upload(client, kb_id, tid, "dup.txt", SAMPLE_TXT)

    # 第二次上传相同内容返回 409
    r = client.post(
        f"/api/kb/{kb_id}/upload",
        data={"tenantId": tid},
        files={"files": ("dup_renamed.txt", io.BytesIO(SAMPLE_TXT), "text/plain")},
        headers=HEADERS,
    )
    assert r.status_code == 409


def test_same_name_different_content_ok(client):
    """文件名相同但内容不同，应视为新文档"""
    tid = make_tenant()
    kb = _create_kb(client, tid)
    kb_id = kb["kbId"]

    _upload(client, kb_id, tid, "doc.txt", SAMPLE_TXT)
    _upload(client, kb_id, tid, "doc.txt", SAMPLE_TXT + b"different_content_here", expected_status=200)


# ── 删除文档 ──────────────────────────────────────────────────

def test_delete_doc_success(client):
    tid = make_tenant()
    kb = _create_kb(client, tid)
    kb_id = kb["kbId"]
    docs = _upload(client, kb_id, tid, "to_delete.txt", SAMPLE_TXT)
    doc_id = docs[0]["docId"]

    r = client.delete(f"/api/kb/{kb_id}/docs/{doc_id}?tenantId={tid}", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # 再查询应返回 404
    r2 = client.get(
        f"/api/kb/{kb_id}/docs/{doc_id}/status?tenantId={tid}",
        headers=HEADERS,
    )
    assert r2.status_code == 404


def test_delete_doc_not_found(client):
    tid = make_tenant()
    kb = _create_kb(client, tid)
    r = client.delete(
        f"/api/kb/{kb['kbId']}/docs/doc_nonexistent?tenantId={tid}",
        headers=HEADERS,
    )
    assert r.status_code == 404


def test_delete_doc_kb_not_found(client):
    tid = make_tenant()
    r = client.delete(
        f"/api/kb/kb_nonexistent/docs/doc_xxx?tenantId={tid}",
        headers=HEADERS,
    )
    assert r.status_code == 404


def test_delete_doc_while_indexing(client):
    """indexing 状态的文档不允许删除，应返回 409"""
    tid = make_tenant()
    kb = _create_kb(client, tid)
    kb_id = kb["kbId"]

    # 手动在 meta 中写入一条 indexing 状态的文档
    from services import meta_store
    import asyncio

    doc_id = "doc_fake_indexing"
    asyncio.run(
        meta_store.add_doc(tid, kb_id, doc_id, "fake.txt", 1, [f"{doc_id}_0"], status="indexing")
    )

    r = client.delete(f"/api/kb/{kb_id}/docs/{doc_id}?tenantId={tid}", headers=HEADERS)
    assert r.status_code == 409


# ── 错误格式文件 ──────────────────────────────────────────────

def test_upload_unsupported_format(client):
    tid = make_tenant()
    kb = _create_kb(client, tid)
    r = client.post(
        f"/api/kb/{kb['kbId']}/upload",
        data={"tenantId": tid},
        files={"files": ("test.docx", io.BytesIO(b"fake docx content"), "application/octet-stream")},
        headers=HEADERS,
    )
    assert r.status_code == 400


def test_upload_kb_not_found(client):
    tid = make_tenant()
    r = client.post(
        "/api/kb/kb_nonexistent/upload",
        data={"tenantId": tid},
        files={"files": ("test.txt", io.BytesIO(SAMPLE_TXT), "text/plain")},
        headers=HEADERS,
    )
    assert r.status_code == 404
