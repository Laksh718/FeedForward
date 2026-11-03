"""Admin daily log: validation, storage, features from admin entries, API, forecast versus actual and the retraining hook."""

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.main import create_app
from feedforward import config as C
from feedforward.admin import review_log
from feedforward.admin.history import admin_history_rows, real_day_count
from feedforward.admin.schemas import DaySaveIn, KitchenRowIn
from feedforward.admin.store import CsvLogStore

pytestmark = pytest.mark.skipif(not (C.MODELS_DIR / "final" / "cvae.pt").exists(), reason="final model missing")
PIN = {"X-Admin-Pin": "1234"}
DAY = "2026-10-06"
ENTRY = {"date": DAY, "entered_by": "tester",
         "context": {"date": DAY, "temp_max_c": 33, "temp_min_c": 26, "weather_type": "Light Rain", "exam_week": True,
                     "exam_type": "formative_test"},
         "attendance": [{"meal_slot": "lunch", "attendance": 3300, "students_present": 3700}],
         "kitchen": [{"meal_slot": "lunch", "dish_id": "D120", "prepared_qty": 3500, "consumed_qty": 3100},
                     {"meal_slot": "lunch", "dish_id": "D076", "prepared_qty": 3300, "leftover_qty": 200, "ran_out_early": False}],
         "ingredients": [{"ingredient": "rice", "used_kg": 950}]}


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    """Every test writes to its own folder, never to data_store/admin_logs."""
    monkeypatch.setattr(C, "ADMIN_LOG_DIR", tmp_path)
    monkeypatch.setattr(review_log, "LOG_PATH", tmp_path / "forecast_log.csv")
    monkeypatch.setenv("ADMIN_PIN", "1234")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GROQ_API_KEY", "")
    return tmp_path


@pytest.fixture()
def client(isolated):
    return TestClient(create_app())


@pytest.mark.parametrize("patch", [
    {"context": {"date": DAY, "temp_max_c": 30, "temp_min_c": 35}},                                 # minimum above maximum
    {"context": {"date": DAY, "temp_max_c": 60}},                                                   # temperature out of range
    {"context": {"date": DAY, "weather_type": "Snow"}},                                             # unknown weather
    {"context": {"date": DAY, "special_day": True}},                                                # type and name missing
    {"attendance": [{"meal_slot": "lunch", "attendance": 4500}]},                                   # more than enrolled
    {"attendance": [{"meal_slot": "lunch", "attendance": 100}, {"meal_slot": "lunch", "attendance": 200}]},
    {"kitchen": [{"meal_slot": "lunch", "dish_id": "D120", "prepared_qty": 100}]},                 # neither eaten nor left over
    {"kitchen": [{"meal_slot": "lunch", "dish_id": "D120", "prepared_qty": 100, "consumed_qty": 150}]},
    {"kitchen": [{"meal_slot": "lunch", "dish_id": "D120", "prepared_qty": -5, "consumed_qty": 1}]},
    {"kitchen": [{"meal_slot": "lunch", "dish_id": "D120", "prepared_qty": 100, "consumed_qty": 60, "leftover_qty": 10}]},
    {"kitchen": [{"meal_slot": "lunch", "dish_id": "D120", "prepared_qty": 100, "consumed_qty": 90, "unmet_qty": 5}]},
    {"kitchen": [{"meal_slot": "lunch", "dish_id": "D120", "prepared_qty": 9, "consumed_qty": 1}] * 2},   # duplicate dish
    {"context": {"date": "2026-10-05"}},                                                            # date mismatch
])
def test_invalid_entries_are_rejected_with_a_message(patch):
    with pytest.raises(ValidationError) as exc:
        DaySaveIn(**{"date": DAY, **patch})
    assert exc.value.errors()[0]["msg"]


def test_valid_entry_and_ran_out_early():
    DaySaveIn(**ENTRY)
    row = KitchenRowIn(meal_slot="dinner", dish_id="D120", prepared_qty=100, consumed_qty=100, ran_out_early=True, unmet_qty=30)
    assert row.unmet_qty == 30


def test_store_saves_updates_and_soft_deletes(isolated):
    store = CsvLogStore()
    store.save_day(DaySaveIn(**ENTRY))
    again = dict(ENTRY, kitchen=[{"meal_slot": "lunch", "dish_id": "D120", "prepared_qty": 3600, "consumed_qty": 3200}])
    store.save_day(DaySaveIn(**again))
    kit = store.read("kitchen_log")
    assert len(kit) == 1 and int(kit.iloc[0]["prepared_qty"]) == 3600      # saving again updates; the dish left out is retired
    assert len(store.read("kitchen_log", include_deleted=True)) == 2 and set(kit["data_source"]) == {"admin_real"}
    assert store.soft_delete("kitchen_log", {"date": DAY, "dish_id": "D120"}) == 1
    assert store.read("kitchen_log").empty and "prepared_qty" in store.export_csv("kitchen_log")


def test_history_rows_mirror_the_dataset_columns(isolated):
    store = CsvLogStore()
    store.save_day(DaySaveIn(**ENTRY))
    rows, skipped = admin_history_rows(store)
    clean = pd.read_parquet(C.PROCESSED_DIR / "kitchen_clean.parquet")
    assert skipped == 0 and set(clean.columns) - {"demand_outlier"} <= set(rows.columns)
    left = rows[rows["dish_id"] == "D076"].iloc[0]
    assert left["consumed_qty"] == 3100 and left["leftover_qty"] == 200 and left["attendance"] == 3300
    assert real_day_count(store) == 1
    no_att = dict(ENTRY, attendance=[])
    other = CsvLogStore(isolated / "other")
    other.save_day(DaySaveIn(**no_att))
    assert admin_history_rows(other)[1] == 2        # rows without an attendance number are skipped, and counted


def test_admin_day_information_flows_into_the_features(isolated):
    from feedforward.data.features import full_calendar, full_weather
    CsvLogStore().save_day(DaySaveIn(**ENTRY))
    cal = full_calendar().set_index("date").loc[pd.Timestamp(DAY)]
    assert cal["formative_test_any"] == 1 and cal["phase_confidence"] == "official"
    w = full_weather(pd.DatetimeIndex([DAY])).iloc[0]
    assert w["temp_max_c"] == 33 and w["rain_level"] == 1 and w["weather_assumed"] == 0


def test_pin_is_required(client, monkeypatch):
    assert client.get("/api/admin/menu", params={"date": DAY}).status_code == 401
    assert client.get("/api/admin/menu", params={"date": DAY}, headers={"X-Admin-Pin": "nope"}).status_code == 401
    assert client.post("/api/admin/login", headers=PIN).json()["ok"] is True
    monkeypatch.setenv("ADMIN_PIN", "change-me")
    r = client.post("/api/admin/login", headers=PIN)
    assert r.status_code == 503 and "ADMIN_PIN" in r.json()["detail"]["fix"]


def test_menu_validate_save_and_read_back(client):
    menu = client.get("/api/admin/menu", params={"date": DAY}, headers=PIN).json()
    assert menu["weekday"] == "Tuesday" and menu["slots"]["lunch"]
    typo = dict(ENTRY, kitchen=[{"meal_slot": "lunch", "dish_id": "D120", "prepared_qty": 3500, "consumed_qty": 31000 // 10 * 10}])
    typo["kitchen"][0].update(prepared_qty=40000, consumed_qty=39000)
    warn = client.post("/api/admin/validate", json=typo, headers=PIN).json()["warnings"]
    assert any("far outside the expected range" in w["message"] for w in warn)
    ok = client.post("/api/admin/day", json=ENTRY, headers=PIN)
    assert ok.status_code == 200 and ok.json()["saved"]["kitchen_log"] == 2
    saved = client.get("/api/admin/day", params={"date": DAY}, headers=PIN).json()
    assert len(saved["kitchen_log"]) == 2 and saved["day_context"][0]["condition"] == "Light Rain"
    recent = client.get("/api/admin/recent", headers=PIN).json()["days"]
    assert recent[0]["date"] == DAY and recent[0]["kitchen_log"] == 2
    csv = client.get("/api/admin/export", params={"table": "attendance"}, headers=PIN)
    assert csv.status_code == 200 and "3300" in csv.text
    assert client.get("/api/admin/export", params={"table": "nope"}, headers=PIN).status_code == 400
    plan = client.get("/api/plan", params={"date": DAY, "slot": "lunch", "scope": "all"}).json()
    assert plan["day_facts"]["temp_max_c"] == 33 and plan["day_facts"]["formative_test"] is True      # the entry flows into the forecast
    gone = client.request("DELETE", "/api/admin/entry", json={"table": "kitchen_log", "date": DAY, "dish_id": "D120", "meal_slot": "lunch"}, headers=PIN)
    assert gone.json()["deleted_rows"] == 1


def test_future_dates_only_take_weather_and_special_day_information(client):
    future = {"date": "2026-10-20", "context": {"date": "2026-10-20", "temp_max_c": 35, "festival": True, "festival_name": "Test day",
                                                 "festival_scale": "major"}}
    assert client.post("/api/admin/day", json=future, headers=PIN).status_code == 200
    bad = dict(future, attendance=[{"meal_slot": "lunch", "attendance": 100}])
    r = client.post("/api/admin/day", json=bad, headers=PIN)
    assert r.status_code == 400 and "future" in r.json()["detail"]["message"]
    plan = client.get("/api/plan", params={"date": "2026-10-20", "slot": "lunch"}).json()
    assert plan["day_facts"]["festival"] is True and plan["day_facts"]["weather_is_assumed"] is False


def test_fill_from_recipes(client):
    r = client.post("/api/admin/fill-recipes", json={"rows": [{"dish_id": "D120", "prepared_qty": 1000}]}, headers=PIN).json()
    assert r["ingredients"] and all(i["used_kg"] >= 0 for i in r["ingredients"])
    assert {i["ingredient"] for i in r["ingredients"]} & {"rice"}


def test_csv_import_attendance(client):
    csv_text = ("date,meal_slot,attendance,students_present\n"
                f"{DAY},lunch,3200,3500\n{DAY},dinner,2900,\n2026-10-02,lunch,99999,\n")
    r = client.post("/api/admin/import", json={"table": "attendance", "csv_text": csv_text}, headers=PIN).json()
    assert r["dates_saved"] == 1 and r["dates"] == [DAY]
    assert len(r["row_errors"]) == 1 and "4000" in r["row_errors"][0]["message"]
    saved = client.get("/api/admin/day", params={"date": DAY}, headers=PIN).json()
    assert {a["meal_slot"]: a["attendance"] for a in saved["attendance"]} == {"lunch": 3200, "dinner": 2900}


def test_csv_import_kitchen_log_future_date_is_rejected(client):
    csv_text = f"date,meal_slot,dish_id,prepared_qty,consumed_qty\n2026-10-20,lunch,D120,3000,2800\n"
    r = client.post("/api/admin/import", json={"table": "kitchen_log", "csv_text": csv_text}, headers=PIN).json()
    assert r["dates_saved"] == 0 and "future" in r["row_errors"][0]["message"]


def test_csv_import_unknown_table_is_rejected(client):
    r = client.post("/api/admin/import", json={"table": "nope", "csv_text": "date\n2026-10-06\n"}, headers=PIN)
    assert r.status_code == 422


def test_forecast_versus_actual(client, isolated):
    client.post("/api/review", json={"date": DAY, "meal_slot": "lunch", "decision": "approve"})
    assert client.get("/api/admin/forecast-vs-actual", headers=PIN).json()["summary"] is None      # no actuals yet
    client.post("/api/admin/day", json=ENTRY, headers=PIN)
    out = client.get("/api/admin/forecast-vs-actual", headers=PIN).json()
    assert out["summary"]["rows"] == 2 and {r["dish_id"] for r in out["rows"]} == {"D120", "D076"}
    assert all(r["actual_demand"] in (3100, 3100) for r in out["rows"])


def test_retraining_hook_uses_real_rows_and_warns(isolated, capsys):
    from feedforward.models.train import load_panel_with_admin
    CsvLogStore().save_day(DaySaveIn(**ENTRY))
    panel = load_panel_with_admin(3.0)
    real = panel[panel["data_source"] == "admin_real"]
    assert len(real) == 2 and set(real["sample_weight"]) == {3.0} and set(panel.loc[panel["data_source"] != "admin_real", "sample_weight"]) == {1.0}
    assert "only 1 real days" in capsys.readouterr().out
