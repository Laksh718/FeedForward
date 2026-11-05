"""Accounts, kitchen documents (RAG) and surplus food donations."""

import base64

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from feedforward import config as C

pytestmark = pytest.mark.skipif(not (C.MODELS_DIR / "final" / "cvae.pt").exists(), reason="final model missing")
SOP = b"""# Surplus SOP

## Holding
Hot food must be held at or above 63 C until it is served. Cold food must be kept below 5 C.

## Donation
Surplus cooked food must be handed over within 3 hours of the end of service. A minimum of 50 portions is worth arranging a pickup.
"""


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from feedforward.admin import review_log
    monkeypatch.setattr(C, "ADMIN_LOG_DIR", tmp_path)
    monkeypatch.setattr(review_log, "LOG_PATH", tmp_path / "forecast_log.csv")
    monkeypatch.setenv("ADMIN_PIN", "1234")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    return TestClient(create_app())


def _register(client, role, email, **extra):
    body = {"email": email, "password": "password1", "name": "N", "org_name": f"Org {email}", "role": role, **extra}
    r = client.post("/api/auth/register", json=body)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["user"]


def test_accounts_kitchen_needs_the_code_and_ngos_wait_for_approval(client):
    bad = client.post("/api/auth/register", json={"email": "k@x.org", "password": "password1", "name": "K", "org_name": "K",
                                                  "role": "kitchen", "invite_code": "0000"})
    assert bad.status_code == 400 and "invite code" in bad.json()["detail"]["message"]
    kitchen, k = _register(client, "kitchen", "k@x.org", invite_code="1234")
    assert k["status"] == "active" and "password" not in k
    ngo, n = _register(client, "ngo", "n@x.org", ngo_type="shelter", capacity=100)
    assert n["status"] == "pending" and n["ngo_type"] == "shelter"
    assert client.post("/api/auth/login", json={"email": "n@x.org", "password": "wrong"}).status_code == 401
    assert client.get("/api/auth/me", headers=ngo).json()["user"]["id"] == n["id"]
    assert client.get("/api/accounts", headers=ngo).status_code == 403                 # only kitchens list accounts
    assert client.get("/api/admin/summary", headers=kitchen).status_code == 200       # a kitchen opens the Daily log
    assert client.get("/api/admin/summary", headers=ngo).status_code == 401
    assert client.post(f"/api/accounts/{n['id']}/status", headers=kitchen, json={"status": "active"}).json()["account"]["status"] == "active"
    client.post("/api/auth/logout", headers=ngo)
    assert client.get("/api/auth/me", headers=ngo).json()["user"] is None


def test_demo_accounts_and_example_ngos(client, monkeypatch):
    r = client.post("/api/auth/demo", json={"role": "kitchen"}).json()
    assert r["user"]["role"] == "kitchen" and r["user"]["demo"] is True
    ngos = client.get("/api/accounts", params={"role": "ngo"}, headers={"Authorization": f"Bearer {r['token']}"}).json()["accounts"]
    assert len(ngos) >= 5 and all(a["status"] == "active" for a in ngos)
    monkeypatch.setenv("FEEDFORWARD_DEMO", "off")
    assert client.post("/api/auth/demo", json={"role": "ngo"}).status_code == 403


def test_documents_are_read_searched_and_their_rules_used(client):
    kitchen, _ = _register(client, "kitchen", "k@x.org", invite_code="1234")
    body = {"filename": "sop.md", "content_base64": base64.b64encode(SOP).decode(), "title": "Surplus SOP"}
    assert client.post("/api/knowledge/upload", json=body).status_code == 401           # signed out: no uploads
    r = client.post("/api/knowledge/upload", headers=kitchen, json=body).json()
    assert r["document"]["passages"] >= 1
    lib = client.get("/api/knowledge").json()
    assert [d["title"] for d in lib["documents"]] == ["Surplus SOP"]
    rules = {x["key"]: x["value"] for x in lib["rules"]}
    assert rules["handover_hours"] == 3 and rules["hot_holding_c"] == 63 and rules["min_donation_portions"] == 50
    hit = client.get("/api/knowledge/search", params={"q": "how long can leftovers wait before donating"}).json()["passages"]
    assert hit and "within 3 hours" in hit[0]["text"]
    ask = client.post("/api/knowledge/ask", json={"question": "When must surplus food be handed over?"}).json()
    assert "3 hours" in ask["answer"] and ask["passages"]
    chat = client.post("/api/chat", json={"question": "What does the SOP say about donating surplus food?", "date": "2026-10-07"}).json()
    assert chat["source"] == "documents" and chat["documents"]
    bad = client.post("/api/knowledge/upload", headers=kitchen, json={"filename": "x.exe", "content_base64": "AAAA"})
    assert bad.status_code == 400
    doc_id = lib["documents"][0]["id"]
    client.delete(f"/api/knowledge/{doc_id}", headers=kitchen)
    assert client.get("/api/knowledge").json()["documents"] == []


def test_donations_from_offer_to_collection(client):
    kitchen, _ = _register(client, "kitchen", "k@x.org", invite_code="1234")
    ngo, n = _register(client, "ngo", "n@x.org")
    other, o = _register(client, "ngo", "o@x.org")
    for acc in (n, o):
        client.post(f"/api/accounts/{acc['id']}/status", headers=kitchen, json={"status": "active"})
    s = client.get("/api/donations/suggest", headers=kitchen, params={"date": "2026-10-07", "slot": "lunch", "source": "plan"}).json()
    assert s["total"] > 0 and "not approved" in s["note"]                              # works before any approval
    offer = client.post("/api/donations", headers=kitchen, json={"date": "2026-10-07", "meal_slot": "lunch", "items": s["items"],
                                                                  "location": "Back gate"}).json()["offer"]
    direct = client.post("/api/donations", headers=kitchen, json={"date": "2026-10-07", "meal_slot": "lunch", "location": "Back gate",
                                                                   "items": [{"dish_id": "D120", "dish_name": "Rice", "portions": 80}],
                                                                   "to_ngo_id": o["id"]}).json()["offer"]
    assert direct["to_ngo"]["id"] == o["id"]
    seen_by_n = {x["id"] for x in client.get("/api/donations", headers=ngo).json()["offers"]}
    assert offer["id"] in seen_by_n and direct["id"] not in seen_by_n                    # sent to another NGO: hidden
    assert client.post(f"/api/donations/{direct['id']}/claim", headers=ngo, json={"portions": 10, "pickup_at": direct["pickup_until"]}).status_code == 400
    r = client.post(f"/api/donations/{offer['id']}/claim", headers=ngo, json={"portions": 100, "pickup_at": offer["pickup_until"]}).json()
    assert r["offer"]["remaining"] == offer["total_portions"] - 100
    cid = r["offer"]["claims"][0]["id"]
    assert client.post(f"/api/donations/{offer['id']}/claims/{cid}", headers=other, json={"action": "accept"}).status_code == 400
    client.post(f"/api/donations/{offer['id']}/claims/{cid}", headers=kitchen, json={"action": "accept"})
    done = client.post(f"/api/donations/{offer['id']}/claims/{cid}", headers=kitchen, json={"action": "collected"}).json()
    assert done["offer"]["claims"][0]["status"] == "collected"
    stats = client.get("/api/donations").json()["stats"]
    assert stats["portions_collected"] == 100 and stats["ngos_helped"] == 1
    assert client.get("/api/donations").json()["offers"][0]["claims"] == []          # signed out: no one's requests
    kinds = [e["kind"] for e in client.get("/api/activity").json()["events"]]
    assert "donation_collected" in kinds and "donation_offer" in kinds
