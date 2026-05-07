"""健康检查接口测试"""
from test.conftest import HEADERS


def test_health_no_auth(client):
    """健康检查无需鉴权"""
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_health_with_auth(client):
    """携带 token 同样正常返回"""
    r = client.get("/api/health", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
