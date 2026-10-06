"""API smoke tests (need the final model: python -m feedforward.models.train --final)."""

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from feedforward import config as C

pytestmark = pytest.mark.skipif(not (C.MODELS_DIR / "final" / "cvae.pt").exists(), reason="final model missing")


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app())


@pytest.fixture()
def isolated_log(tmp_path, monkeypatch):
    from feedforward.admin import review_log
    monkeypatch.setattr(review_log, "LOG_PATH", tmp_path / "forecast_log.csv")


def test_health(client):
    r = client.get("/api/health").json()
    assert r["status"] == "ok" and r["default_plan_date"] == "2026-10-07" and "Simulated" in r["data_source_chip"]


def test_plan_core_and_all(client):
    core = client.get("/api/plan", params={"date": "2026-10-07", "slot": "lunch"}).json()
    full = client.get("/api/plan", params={"date": "2026-10-07", "slot": "lunch", "scope": "all"}).json()
    assert core["dishes"] and all(d["is_core"] for d in core["dishes"])
    assert len(full["dishes"]) > len(core["dishes"]) and core["dishes_hidden"] == len(full["dishes"]) - len(core["dishes"])
    assert core["totals"]["recommended"] == sum(d["recommended"] for d in core["dishes"])
    assert core["headline"].startswith("Cook ") and "portions for lunch" in core["headline"]
    assert core["headline"].endswith("than the usual plan.") or "usual plan" in core["headline"]
    assert core["weekday"] == "Wednesday"


def test_week(client):
    w = client.get("/api/week", params={"slot": "lunch", "start": "2026-10-07"}).json()
    assert len(w["days"]) == 7 and len(w["past"]) == 6  # 2026-10-06 (today) is not recorded yet
    assert all(d["p10"] <= d["p50"] <= d["p90"] for d in w["days"])
    one = client.get("/api/week", params={"slot": "lunch", "start": "2026-10-07", "dish_id": "D090"}).json()
    assert one["scope"] == "dish"


def test_whatif(client):
    r = client.post("/api/whatif", json={"date": "2026-10-07", "meal_slot": "lunch", "overrides": {"attendance_change_pct": 15}})
    body = r.json()
    assert r.status_code == 200 and body["difference"]["p50"] > 0
    assert body["changed"]["overrides_applied"] == {"attendance_change_pct": 15.0}


@pytest.mark.parametrize("payload", [
    {"date": "2026-10-07", "meal_slot": "lunch", "overrides": {"temp_min_c": 40, "temp_max_c": 30}},
    {"date": "2026-10-07", "meal_slot": "lunch", "overrides": {"weather_type": "Snow"}},
    {"date": "2026-10-07", "meal_slot": "brunch"},
    {"date": "2026-10-07", "meal_slot": "lunch", "overrides": {"expected_attendance": 99999}},
])
def test_whatif_validation(client, payload):
    r = client.post("/api/whatif", json=payload)
    assert r.status_code == 422 and r.json()["detail"]["fix"] and r.json()["detail"]["fields"]


def test_date_outside_calendar_is_friendly(client):
    r = client.get("/api/plan", params={"date": "2030-01-01", "slot": "lunch"})
    assert r.status_code == 400 and "fix" in r.json()["detail"]


def test_review_stores_snapshot(client, isolated_log):
    body = {"date": "2026-10-07", "meal_slot": "lunch", "decision": "approve", "reviewer": "test"}
    assert client.get("/api/review", params={"date": "2026-10-07", "slot": "lunch"}).json()["review"] is None
    r = client.post("/api/review", json=body).json()
    assert r["stored_rows"] > 0 and r["review"]["decision"] == "approve"
    again = client.post("/api/review", json=dict(body, decision="send_back")).json()
    assert again["review"]["decision"] == "send_back"
    assert client.post("/api/review", json=dict(body, decision="maybe")).status_code == 422
    assert client.post("/api/review", json=dict(body, adjusted_quantities={"D999": 5})).status_code == 400
    assert client.post("/api/review", json=dict(body, adjusted_quantities={"D053": -1})).status_code == 422
    ok = client.post("/api/review", json=dict(body, adjusted_quantities={"D053": 3000})).json()
    assert ok["stored_rows"] > 0
    import pandas as pd

    from feedforward.admin import review_log
    log = pd.read_csv(review_log.LOG_PATH)
    row = log[(log["dish_id"] == "D053") & (log["decision"] == "approve")].iloc[-1]
    assert row["approved_qty"] == 3000


def test_catalogues(client):
    assert client.get("/api/dishes").json()["count"] == 151
    menu = client.get("/api/dishes", params={"date": "2026-10-07", "slot": "lunch"}).json()
    assert 0 < menu["count"] < 151
    assert client.get("/api/ingredients").json()["count"] == 70
