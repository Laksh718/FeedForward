"""Surplus food donations from kitchens to NGOs and help groups.

A kitchen posts an offer: the dishes and portions it can give, where, and until when food can be collected. It can fill
the offer from what the Daily log says was left over, or from the surplus an approved plan is expected to leave
(approved quantity minus the most likely demand). The collection deadline defaults to the hand over rule found in the
kitchen's documents (feedforward.community.knowledge), or 2 hours.

An approved NGO requests some or all of the remaining portions with a pickup time; the kitchen accepts or declines, and
marks the request collected when the food has gone. An offer closes when everything is spoken for, when the kitchen
cancels it, or when its deadline passes.

Stored in donations.json in the admin log folder; every change shows in the activity feed of every view.
"""

import json
import secrets
import threading
from datetime import datetime, timedelta

from feedforward import config as C

DEFAULT_HANDOVER_HOURS = 2
CLAIM_ACTIONS = {"accept": "accepted", "decline": "declined", "collected": "collected"}
_lock = threading.RLock()


class DonationError(ValueError):
    """A donation request that cannot be done, with a message for the person."""


def _path():
    return C.ADMIN_LOG_DIR / "donations.json"


def _read() -> dict:
    p = _path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write(data: dict) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    tmp.replace(p)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _held(offer: dict) -> int:
    """Portions already spoken for: requested, accepted or collected."""
    return sum(c["portions"] for c in offer["claims"] if c["status"] in ("requested", "accepted", "collected"))


def _refresh(offer: dict) -> dict:
    """Remaining portions and the status that follows from the claims and the deadline."""
    offer["remaining"] = max(0, offer["total_portions"] - _held(offer))
    if offer["status"] in ("cancelled", "completed"):
        return offer
    active = [c for c in offer["claims"] if c["status"] in ("requested", "accepted")]
    if not active and any(c["status"] == "collected" for c in offer["claims"]) and offer["remaining"] == 0:
        offer["status"] = "completed"
    elif offer["pickup_until"] < _now() and not active:
        offer["status"] = "completed" if any(c["status"] == "collected" for c in offer["claims"]) else "expired"
    else:
        offer["status"] = "open" if offer["remaining"] > 0 else "spoken_for"
    return offer


def offers(status: str | None = None, ngo_id: str | None = None) -> list[dict]:
    """Every offer, newest first, with its remaining portions. ngo_id keeps only that NGO's claims (privacy) and leaves
    out offers the kitchen sent to another NGO."""
    out = []
    for o in _read().values():
        o = _refresh(o)
        to = o.get("to_ngo")
        if ngo_id is not None and to and to["id"] != ngo_id:
            continue
        if ngo_id is not None:
            o = dict(o, claims=[c for c in o["claims"] if c["ngo_id"] == ngo_id])
        if status is None or o["status"] == status:
            out.append(o)
    return sorted(out, key=lambda o: o["created_at"], reverse=True)


def create_offer(kitchen: dict, date: str, meal_slot: str, items: list[dict], pickup_until: str | None, location: str,
                 notes: str = "", handover_hours: float | None = None, to_ngo: dict | None = None) -> dict:
    """A kitchen offers surplus food. items: [{dish_id, dish_name, portions}]; portions above zero only.
    to_ngo (an approved NGO account) sends the offer to that NGO only; without it every approved NGO sees it."""
    if to_ngo is not None and (to_ngo.get("role") != "ngo" or to_ngo.get("status") != "active"):
        raise DonationError("Choose an approved NGO to send the food to.")
    items = [{"dish_id": i.get("dish_id", ""), "dish_name": str(i.get("dish_name", ""))[:80], "portions": int(i["portions"])}
             for i in items if int(i.get("portions") or 0) > 0]
    if not items:
        raise DonationError("Add at least one dish with portions to give.")
    hours = handover_hours or DEFAULT_HANDOVER_HOURS
    until = pickup_until or (datetime.now() + timedelta(hours=hours)).isoformat(timespec="minutes")
    if until <= _now():
        raise DonationError("The collection deadline is already past. Choose a later time.")
    if not location.strip():
        raise DonationError("Say where the food can be collected.")
    with _lock:
        data = _read()
        oid = secrets.token_hex(5)
        data[oid] = {"id": oid, "created_at": _now(), "kitchen_id": kitchen["id"], "kitchen_name": kitchen["org_name"],
                     "contact": kitchen.get("phone", ""), "date": date, "meal_slot": meal_slot, "items": items,
                     "total_portions": sum(i["portions"] for i in items), "pickup_until": until, "location": location.strip()[:200],
                     "notes": notes.strip()[:500], "handover_hours": hours, "status": "open", "claims": [],
                     "to_ngo": {"id": to_ngo["id"], "org_name": to_ngo["org_name"], "area": to_ngo.get("area", ""),
                                "ngo_type": to_ngo.get("ngo_type")} if to_ngo else None}
        _write(data)
        return _refresh(data[oid])


def claim(offer_id: str, ngo: dict, portions: int, pickup_at: str, note: str = "") -> dict:
    """An approved NGO asks for some of the remaining portions."""
    if ngo["role"] != "ngo":
        raise DonationError("Only NGO accounts request food.")
    if ngo["status"] != "active":
        raise DonationError("Your account is waiting for a kitchen to approve it. You can request food once it is approved.")
    with _lock:
        data = _read()
        o = data.get(offer_id)
        if o is None:
            raise DonationError("No such offer.")
        _refresh(o)
        if o["status"] != "open":
            raise DonationError("This offer is no longer open.")
        if o.get("to_ngo") and o["to_ngo"]["id"] != ngo["id"]:
            raise DonationError(f"This food was sent to {o['to_ngo']['org_name']}.")
        if not 0 < portions <= o["remaining"]:
            raise DonationError(f"Ask for between 1 and {o['remaining']} portions.")
        if pickup_at > o["pickup_until"]:
            raise DonationError(f"Collect the food before {o['pickup_until'].replace('T', ' ')}.")
        o["claims"].append({"id": secrets.token_hex(4), "ngo_id": ngo["id"], "ngo_name": ngo["org_name"], "contact": ngo.get("phone", ""),
                            "portions": int(portions), "pickup_at": pickup_at, "note": note.strip()[:300], "status": "requested",
                            "created_at": _now(), "updated_at": _now()})
        _write(data)
        return _refresh(o)


def act_on_claim(offer_id: str, claim_id: str, action: str, user: dict) -> dict:
    """The kitchen accepts, declines or marks collected; the NGO may withdraw its own request (decline)."""
    if action not in CLAIM_ACTIONS:
        raise DonationError(f"Action must be one of {list(CLAIM_ACTIONS)}.")
    with _lock:
        data = _read()
        o = data.get(offer_id)
        c = next((c for c in (o or {}).get("claims", []) if c["id"] == claim_id), None)
        if c is None:
            raise DonationError("No such request.")
        own_kitchen = user["role"] == "kitchen" and user["id"] == o["kitchen_id"]
        own_ngo = user["role"] == "ngo" and user["id"] == c["ngo_id"]
        if not (own_kitchen or (own_ngo and action == "decline")):
            raise DonationError("Only the kitchen that made the offer can do this.")
        allowed = {"accept": ("requested",), "decline": ("requested", "accepted"), "collected": ("requested", "accepted")}
        if c["status"] not in allowed[action]:
            raise DonationError(f"This request is already {c['status']}.")
        c["status"], c["updated_at"] = CLAIM_ACTIONS[action], _now()
        if own_ngo:
            c["status"] = "withdrawn"
        _write(data)
        return _refresh(o)


def cancel(offer_id: str, kitchen: dict) -> dict:
    with _lock:
        data = _read()
        o = data.get(offer_id)
        if o is None or o["kitchen_id"] != kitchen["id"]:
            raise DonationError("Only the kitchen that made the offer can cancel it.")
        o["status"] = "cancelled"
        for c in o["claims"]:
            if c["status"] in ("requested", "accepted"):
                c["status"], c["updated_at"] = "declined", _now()
        _write(data)
        return _refresh(o)


def stats() -> dict:
    """Totals for the dashboard: portions offered, collected, and how many NGOs took part."""
    all_offers = offers()
    collected = [c for o in all_offers for c in o["claims"] if c["status"] == "collected"]
    return {"offers": len(all_offers), "open": sum(o["status"] == "open" for o in all_offers),
            "portions_offered": sum(o["total_portions"] for o in all_offers), "portions_collected": sum(c["portions"] for c in collected),
            "ngos_helped": len({c["ngo_id"] for c in collected})}


def events(limit: int = 50) -> list[dict]:
    """Donation happenings for the activity feed."""
    out = []
    for o in _read().values():
        out.append({"kind": "donation_offer", "at": o["created_at"], "date": o["date"], "meal_slot": o["meal_slot"],
                    "who": o["kitchen_name"], "portions": o["total_portions"]})
        for c in o["claims"]:
            out.append({"kind": f"donation_{c['status']}", "at": c["updated_at"], "date": o["date"], "meal_slot": o["meal_slot"],
                        "who": c["ngo_name"], "portions": c["portions"]})
    return sorted(out, key=lambda e: e["at"], reverse=True)[:limit]
