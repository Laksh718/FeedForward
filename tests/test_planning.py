"""Planning across days: the plans board, decisions on many plans, rare event plans, automation and the activity feed."""

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from feedforward import config as C

pytestmark = pytest.mark.skipif(not (C.MODELS_DIR / "final" / "cvae.pt").exists(), reason="final model missing")
PIN = {"X-Admin-Pin": "1234"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from feedforward.admin import review_log
    monkeypatch.setattr(C, "ADMIN_LOG_DIR", tmp_path)
    monkeypatch.setattr(review_log, "LOG_PATH", tmp_path / "forecast_log.csv")
    monkeypatch.setenv("ADMIN_PIN", "1234")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    return TestClient(create_app())


def test_plans_board_lists_every_meal_with_its_status(client):
    r = client.get("/api/plans", params={"start": "2026-10-07", "days": 3}).json()
    assert [d["date"] for d in r["days"]] == ["2026-10-07", "2026-10-08", "2026-10-09"]
    assert r["summary"]["pending"] == r["summary"]["plans"] > 0 and r["summary"]["approved"] == 0
    lunch = r["days"][0]["slots"][1]
    assert lunch["meal_slot"] == "lunch" and lunch["review"] is None and lunch["totals"]["recommended"] == 12250
    assert r["automation"]["auto_approve"] is False


def test_many_decisions_and_withdraw(client):
    items = [{"date": "2026-10-07", "meal_slot": s} for s in ("lunch", "dinner")]
    assert client.post("/api/plans/review", json={"items": items, "decision": "approve"}).json()["done"] == items
    again = client.post("/api/plans/review", json={"items": items[:1], "decision": "approve"}).json()
    assert again["done"] == [] and again["skipped"] == items[:1]          # an approved plan keeps its quantities
    client.post("/api/plans/review", json={"items": items[1:], "decision": "withdraw"})
    assert client.get("/api/review", params={"date": "2026-10-07", "slot": "dinner"}).json()["review"] is None
    lunch = client.get("/api/plan", params={"date": "2026-10-07", "slot": "lunch"}).json()["review"]
    assert lunch["decision"] == "approve" and lunch["approved_total"] == 12250
    marks = client.get("/api/reviews", params={"start": "2026-10-01", "end": "2026-10-31"}).json()["reviews"]
    assert list(marks) == ["2026-10-07"] and list(marks["2026-10-07"]) == ["lunch"]
    kinds = [e["kind"] for e in client.get("/api/activity").json()["events"]]
    assert kinds[0] == "withdraw" and kinds.count("approve") == 2


def test_forecast_days_has_every_dish_on_every_day(client):
    r = client.get("/api/forecast/days", params={"slot": "lunch", "start": "2026-10-07", "days": 7}).json()
    assert len(r["days"]) == 7
    for day in r["days"]:
        assert sum(d["days"][day["date"]]["recommended"] for d in r["dishes"] if day["date"] in d["days"]) == day["totals"]["recommended"]


def test_rare_event_plan_and_its_approval(client):
    r = client.post("/api/events/plan", json={"date": "2026-10-20", "meal_slot": "lunch", "event": "festival"}).json()
    assert r["overrides"] == {"festival": True} and r["plan"]["totals"]["recommended"] < r["normal"]["totals"]["recommended"]
    assert set(r["options"]) == {"forecast", "generated_typical", "generated_high"}
    if r["generated"]["available"]:
        t = r["generated"]["total"]
        assert t["p10"] <= t["p50"] <= t["p90"] and sum(b["count"] for b in t["histogram"]) == r["generated"]["draws"]
        assert sum(r["verdicts"].values()) == len(r["dishes"])
    ok = client.post("/api/review", json={"date": "2026-10-20", "meal_slot": "lunch", "decision": "approve", "overrides": r["approve_with"]["overrides"],
                                          "note": r["approve_with"]["note"], "adjusted_quantities": r["options"]["generated_high"]}).json()
    assert ok["review"]["approved_total"] == r["option_totals"]["generated_high"] and ok["review"]["overrides"] == {"festival": True}
    many = client.post("/api/events/approve", json={"start": "2026-11-25", "days": 2, "meal_slots": ["lunch", "dinner"],
                                                     "event": "exam_week"}).json()
    assert len(many["done"]) == 4
    assert client.post("/api/events/plan", json={"date": "2026-10-20", "meal_slot": "lunch", "event": "meteor"}).status_code == 422


def test_automation_approves_ahead_and_fills_the_log_without_teaching_the_model(client):
    from feedforward.admin.history import real_day_count
    from feedforward.admin.store import AUTO_SOURCE, get_store
    client.post("/api/plans/review", json={"items": [{"date": "2026-10-07", "meal_slot": "snacks"}], "decision": "send_back"})
    off = client.post("/api/admin/automation/run", headers=PIN).json()
    assert off["result"]["approved"] == [] and "off" in off["message"]
    r = client.post("/api/admin/automation", headers=PIN, json={"auto_approve": True, "auto_log": True, "days_ahead": 2}).json()
    assert len(r["result"]["approved"]) == 7                                # today and tomorrow, minus the plan sent back
    assert r["result"]["left_for_a_person"] == [{"date": "2026-10-07", "meal_slot": "snacks"}]
    assert r["result"]["logged_dates"] == ["2026-10-06"]
    kit = get_store().read("kitchen_log")
    assert len(kit) > 0 and (kit["data_source"] == AUTO_SOURCE).all()
    assert real_day_count() == 0                                            # the model does not learn from automatic fills
    assert client.get("/api/admin/recent", headers=PIN).json()["days"][0]["auto_filled"] is True
    assert client.get("/api/admin/forecast-vs-actual", headers=PIN).json()["summary"] is None
    second = client.post("/api/admin/automation/run", headers=PIN).json()["result"]
    assert second["approved"] == [] and second["logged_dates"] == []      # nothing twice
    fill = client.get("/api/admin/plan-fill", headers=PIN, params={"date": "2026-10-06"}).json()
    assert fill["slots"] == list(C.MEAL_SLOTS) and fill["entry"]["kitchen"]
    assert client.post("/api/admin/automation", headers=PIN, json={"days_ahead": 30}).status_code == 422
