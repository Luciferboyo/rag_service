"""知识库 CRUD 接口测试"""
import pytest
from test.conftest import HEADERS, make_tenant


# ── 辅助函数 ──────────────────────────────────────────────────

def create_kb(client, tenant_id: str, name: str = "测试KB", description: str | None = None) -> dict:
    body = {"tenantId": tenant_id, "name": name}
    if description:
        body["description"] = description
    r = client.post("/api/kb/create", json=body, headers=HEADERS)
    assert r.status_code == 200, r.text
    return r.json()


# ── 鉴权测试 ──────────────────────────────────────────────────

def test_create_kb_requires_auth(client):
    r = client.post("/api/kb/create", json={"tenantId": "x", "name": "y"})
    assert r.status_code == 401


def test_list_kbs_requires_auth(client):
    r = client.get("/api/kb/list?tenantId=x")
    assert r.status_code == 401


# ── 创建知识库 ────────────────────────────────────────────────

def test_create_kb_success(client):
    tid = make_tenant()
    data = create_kb(client, tid, name="法律知识库", description="测试描述")
    assert data["kbId"].startswith("kb_")
    assert data["tenantId"] == tid
    assert data["name"] == "法律知识库"


def test_create_kb_no_description(client):
    tid = make_tenant()
    data = create_kb(client, tid, name="无描述KB")
    assert data["kbId"].startswith("kb_")
    assert data.get("description") is None


# ── 列出知识库 ────────────────────────────────────────────────

def test_list_kbs_empty(client):
    tid = make_tenant()
    r = client.get(f"/api/kb/list?tenantId={tid}", headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_list_kbs_after_create(client):
    tid = make_tenant()
    create_kb(client, tid, name="KB1")
    create_kb(client, tid, name="KB2")
    r = client.get(f"/api/kb/list?tenantId={tid}", headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 2
    names = [kb["name"] for kb in data["items"]]
    assert "KB1" in names
    assert "KB2" in names
    # list 视图只返回 docCount，不含完整文档列表
    for item in data["items"]:
        assert "docCount" in item
        assert "docs" not in item


def test_list_kbs_pagination(client):
    tid = make_tenant()
    for i in range(5):
        create_kb(client, tid, name=f"KB{i}")
    r = client.get(f"/api/kb/list?tenantId={tid}&page=1&pageSize=3", headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 5
    assert data["page"] == 1
    assert data["pageSize"] == 3
    assert len(data["items"]) == 3


def test_list_kbs_invalid_page(client):
    tid = make_tenant()
    r = client.get(f"/api/kb/list?tenantId={tid}&page=0", headers=HEADERS)
    assert r.status_code == 400


def test_create_kb_empty_name(client):
    """name 为空字符串应返回 422"""
    tid = make_tenant()
    r = client.post("/api/kb/create", json={"tenantId": tid, "name": ""}, headers=HEADERS)
    assert r.status_code == 422


def test_create_kb_empty_tenant(client):
    """tenantId 为空字符串应返回 422"""
    r = client.post("/api/kb/create", json={"tenantId": "", "name": "KB"}, headers=HEADERS)
    assert r.status_code == 422


# ── 更新知识库 ────────────────────────────────────────────────

def test_patch_kb_name(client):
    tid = make_tenant()
    kb = create_kb(client, tid, name="旧名称")
    kb_id = kb["kbId"]

    r = client.patch(
        f"/api/kb/{kb_id}",
        json={"tenantId": tid, "name": "新名称"},
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["name"] == "新名称"


def test_patch_kb_description(client):
    tid = make_tenant()
    kb = create_kb(client, tid, name="KB", description="旧描述")
    kb_id = kb["kbId"]

    r = client.patch(
        f"/api/kb/{kb_id}",
        json={"tenantId": tid, "description": "新描述"},
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["description"] == "新描述"


def test_patch_kb_not_found(client):
    tid = make_tenant()
    r = client.patch(
        "/api/kb/kb_nonexistent",
        json={"tenantId": tid, "name": "x"},
        headers=HEADERS,
    )
    assert r.status_code == 404


def test_patch_kb_no_fields(client):
    """name 和 description 都不传应返回 400"""
    tid = make_tenant()
    kb = create_kb(client, tid)
    r = client.patch(
        f"/api/kb/{kb['kbId']}",
        json={"tenantId": tid},
        headers=HEADERS,
    )
    assert r.status_code == 400


# ── 删除知识库 ────────────────────────────────────────────────

def test_delete_kb_success(client):
    tid = make_tenant()
    kb = create_kb(client, tid)
    kb_id = kb["kbId"]

    r = client.delete(f"/api/kb/{kb_id}?tenantId={tid}", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # 删除后不再出现在列表中
    r2 = client.get(f"/api/kb/list?tenantId={tid}", headers=HEADERS)
    kb_ids = [k["kbId"] for k in r2.json()["items"]]
    assert kb_id not in kb_ids


def test_delete_kb_not_found(client):
    tid = make_tenant()
    r = client.delete(f"/api/kb/kb_nonexistent?tenantId={tid}", headers=HEADERS)
    assert r.status_code == 404


# ── 文档列表 ──────────────────────────────────────────────────

def test_list_docs_empty(client):
    tid = make_tenant()
    kb = create_kb(client, tid)
    r = client.get(f"/api/kb/{kb['kbId']}/docs?tenantId={tid}", headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_list_docs_kb_not_found(client):
    tid = make_tenant()
    r = client.get(f"/api/kb/kb_nonexistent/docs?tenantId={tid}", headers=HEADERS)
    assert r.status_code == 404


def test_get_kb_detail(client):
    tid = make_tenant()
    kb = create_kb(client, tid, name="详情KB", description="测试描述")
    r = client.get(f"/api/kb/{kb['kbId']}?tenantId={tid}", headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data["kbId"] == kb["kbId"]
    assert data["name"] == "详情KB"
    assert data["description"] == "测试描述"
    assert "docs" in data


def test_get_kb_detail_not_found(client):
    tid = make_tenant()
    r = client.get(f"/api/kb/kb_nonexistent?tenantId={tid}", headers=HEADERS)
    assert r.status_code == 404
