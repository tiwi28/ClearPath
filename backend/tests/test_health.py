from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_barriers_mock_shape():
    body = client.get("/barriers").json()
    assert body["type"] == "FeatureCollection"


def test_route_accepts_contract_keys():
    # Contract uses "from" (a Python keyword), mapped to from_ via alias.
    payload = {"from": [-79.3832, 43.6532], "to": [-79.377, 43.659], "profile": "wheelchair"}
    assert client.post("/route", json=payload).status_code == 200
