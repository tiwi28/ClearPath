from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_barriers_mock_shape():
    body = client.get("/barriers").json()
    assert body["type"] == "FeatureCollection"


def test_plan_accepts_contract_keys():
    # Contract uses "from" (a Python keyword), mapped to from_ via alias.
    payload = {"from": [-79.41, 43.66], "to": [-79.42, 43.665], "profile": "manual_wheelchair", "include_transit": False}
    assert client.post("/plan", json=payload).status_code == 200
