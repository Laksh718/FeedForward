"""Accounts, kitchen documents (RAG) and surplus food donations.

/api/auth/register, /login, /logout, /me     accounts for kitchens (invite code = ADMIN_PIN) and NGOs (approved by a kitchen)
/api/accounts, /api/accounts/{id}/status     a kitchen lists accounts and approves or switches off NGO accounts
/api/knowledge...                            upload, list, delete and search documents; ask them a question; rules found
/api/donations...                            offers of surplus food, suggestions from the log or the plan, requests, stats

Sessions travel as "Authorization: Bearer <token>". Errors say what happened and how to fix it.
"""

import base64
import binascii
import os
from datetime import date as Date

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, Field

from api.deps import error, get_service
from api.schemas import Slot, check_date
from feedforward.admin.review_log import latest_review
from feedforward.admin.store import get_store
from feedforward.community import accounts, donations, knowledge
from feedforward.models.forecast_service import ForecastService, Overrides

router = APIRouter()


def _token(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def optional_user(authorization: str | None = Header(None)) -> dict | None:
    return accounts.user_for(_token(authorization))


def current_user(user: dict | None = Depends(optional_user)) -> dict:
    if user is None:
        raise error(401, "Please sign in first.", "Open Account (top right), sign in or create an account, then try again.")
    return user


def kitchen_user(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "kitchen":
        raise error(403, "Only kitchen accounts can do this.", "Sign in with the kitchen's account.")
    return user


def kitchen_or_pin(authorization: str | None = Header(None), x_admin_pin: str | None = Header(None)) -> dict:
    """A kitchen session, or the admin PIN (as on the Daily log), may manage documents."""
    user = accounts.user_for(_token(authorization))
    if user and user["role"] == "kitchen":
        return user
    pin = os.getenv("ADMIN_PIN", "").strip()
    if pin and pin != "change-me" and x_admin_pin and x_admin_pin == pin:
        return {"id": "pin", "org_name": "Kitchen admin (PIN)", "role": "kitchen", "name": "Kitchen admin"}
    raise error(401, "Sign in with a kitchen account (or unlock the Daily log with the PIN) to change documents.",
                "Open Account (top right) and sign in.")


def _bad(exc: ValueError):
    return error(400, str(exc), "Change the input and try again.")


# ---------- accounts

class RegisterIn(BaseModel):
    email: str = Field(max_length=120)
    password: str = Field(min_length=1, max_length=200)
    name: str = Field(max_length=80)
    org_name: str = Field(max_length=120)
    role: str = Field(pattern="^(kitchen|ngo)$")
    invite_code: str | None = Field(None, max_length=200)
    phone: str = Field("", max_length=40)
    area: str = Field("", max_length=120)
    capacity: int | None = Field(None, ge=1, le=50000)
    ngo_type: str | None = Field(None, max_length=40)


class LoginIn(BaseModel):
    email: str = Field(max_length=120)
    password: str = Field(max_length=200)


@router.post("/auth/register")
def register(body: RegisterIn) -> dict:
    try:
        user = accounts.register(**body.model_dump(), admin_pin=os.getenv("ADMIN_PIN", "").strip())
        token, user = accounts.login(body.email, body.password)
    except accounts.AccountError as exc:
        raise _bad(exc) from exc
    waiting = " It can request food once a kitchen approves it." if user["status"] == "pending" else ""
    return {"token": token, "user": user, "message": f"Account created for {user['org_name']}.{waiting}"}


def demo_enabled() -> bool:
    """The one click demo accounts are on unless FEEDFORWARD_DEMO=off (switch them off for a real kitchen: the demo
    kitchen can open the Daily log)."""
    return os.getenv("FEEDFORWARD_DEMO", "on").strip().lower() != "off"


class DemoIn(BaseModel):
    role: str = Field(pattern="^(kitchen|ngo)$")


@router.post("/auth/demo")
def demo(body: DemoIn) -> dict:
    """Sign in to the shared demo kitchen or demo NGO, no password needed."""
    if not demo_enabled():
        raise error(403, "The demo accounts are switched off on this server.", "Sign in with your own account, or create one.")
    accounts.ensure_demo_ngos()
    token, user = accounts.demo_login(body.role)
    return {"token": token, "user": user, "message": f"Signed in as {user['org_name']}. This is a shared demo account."}


@router.get("/auth/options")
def options() -> dict:
    """What the sign in page can offer."""
    return {"demo": demo_enabled(), "ngo_types": accounts.NGO_TYPES}


@router.post("/auth/login")
def login(body: LoginIn) -> dict:
    try:
        token, user = accounts.login(body.email, body.password)
    except accounts.AccountError as exc:
        raise error(401, str(exc), "Check the email and password, or create an account.") from exc
    return {"token": token, "user": user, "message": f"Signed in as {user['name']} ({user['org_name']})."}


@router.post("/auth/logout")
def logout(authorization: str | None = Header(None)) -> dict:
    accounts.logout(_token(authorization) or "")
    return {"message": "Signed out."}


@router.get("/auth/me")
def me(user: dict | None = Depends(optional_user)) -> dict:
    return {"user": user}


@router.get("/accounts")
def list_accounts(role: str | None = Query(None, pattern="^(kitchen|ngo)$"), _: dict = Depends(kitchen_user)) -> dict:
    if demo_enabled():
        accounts.ensure_demo_ngos()
    return {"accounts": accounts.list_accounts(role), "ngo_types": accounts.NGO_TYPES}


class StatusIn(BaseModel):
    status: str = Field(pattern="^(active|disabled)$")


@router.post("/accounts/{account_id}/status")
def set_status(account_id: str, body: StatusIn, user: dict = Depends(kitchen_user)) -> dict:
    try:
        acc = accounts.set_status(account_id, body.status, user)
    except accounts.AccountError as exc:
        raise _bad(exc) from exc
    verb = "approved" if body.status == "active" else "switched off"
    return {"account": acc, "message": f"{acc['org_name']} {verb}."}


# ---------- documents

class UploadIn(BaseModel):
    filename: str = Field(min_length=3, max_length=160)
    content_base64: str = Field(min_length=4, max_length=18_000_000)
    title: str = Field("", max_length=160)
    category: str = Field("sop", pattern="^(sop|food_safety|donation|menu|other)$")


@router.get("/knowledge")
def library() -> dict:
    return {"documents": knowledge.documents(), **knowledge.summary()}


@router.post("/knowledge/upload")
def upload(body: UploadIn, user: dict = Depends(kitchen_or_pin)) -> dict:
    try:
        data = base64.b64decode(body.content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise error(400, "The file did not arrive in one piece.", "Choose the file again and upload it.") from exc
    try:
        doc = knowledge.add_document(body.filename, data, body.title, body.category, user["org_name"])
    except knowledge.DocumentError as exc:
        raise _bad(exc) from exc
    return {"document": doc, "message": f"Added {doc['title']}: {doc['passages']} passages from {doc['pages']} page(s)."}


@router.delete("/knowledge/{doc_id}")
def remove(doc_id: str, _: dict = Depends(kitchen_or_pin)) -> dict:
    try:
        knowledge.delete_document(doc_id)
    except knowledge.DocumentError as exc:
        raise _bad(exc) from exc
    return {"message": "Document removed."}


@router.get("/knowledge/search")
def search(q: str = Query(min_length=2, max_length=300), k: int = Query(5, ge=1, le=10)) -> dict:
    return {"question": q, "passages": knowledge.search(q, k)}


class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=500)


@router.post("/knowledge/ask")
def ask(body: AskIn) -> dict:
    """An answer from the documents only: the language model when one is set up (it must stay inside the passages),
    otherwise the best passages themselves."""
    from feedforward.copilot import llm
    from feedforward.copilot.explain import ungrounded_numbers

    passages = knowledge.search(body.question, k=4)
    if not passages:
        return {"answer": "Nothing in the uploaded documents matches this question. Upload the SOP that covers it, or ask in other words.",
                "source": "documents", "passages": []}
    numbered = "\n\n".join(f"[{i + 1}] {p['title']}, page {p['page']}: {p['text']}" for i, p in enumerate(passages))
    fallback = f"From {passages[0]['title']} (page {passages[0]['page']}): {passages[0]['text']}"
    messages = [{"role": "system", "content": "You answer questions for a mess kitchen using ONLY the numbered passages from its own "
                 "documents. Quote numbers exactly as written. Say which passage you used, like [1]. If the passages do not answer "
                 "the question, say so. At most 90 words, plain sentences."},
                {"role": "user", "content": f"PASSAGES:\n{numbered}\n\nQUESTION: {body.question}"}]
    try:
        text = llm.complete(messages)
    except llm.LLMUnavailable as exc:
        return {"answer": fallback, "source": "documents", "passages": passages, "reason": str(exc)}
    if ungrounded_numbers(text, {"passages": [p["text"] for p in passages], "n": list(range(1, len(passages) + 1))}):
        return {"answer": fallback, "source": "documents", "passages": passages, "reason": "the model quoted a figure not in the documents"}
    return {"answer": text, "source": "llm", "passages": passages}


# ---------- donations

class OfferIn(BaseModel):
    date: Date
    meal_slot: Slot
    items: list[dict] = Field(min_length=1, max_length=60)
    pickup_until: str | None = Field(None, max_length=25)
    location: str = Field(max_length=200)
    notes: str = Field("", max_length=500)
    to_ngo_id: str | None = Field(None, max_length=40)


class ClaimIn(BaseModel):
    portions: int = Field(ge=1, le=50000)
    pickup_at: str = Field(max_length=25)
    note: str = Field("", max_length=300)


class ClaimActionIn(BaseModel):
    action: str = Field(pattern="^(accept|decline|collected)$")


@router.get("/donations")
def list_offers(status: str | None = None, user: dict | None = Depends(optional_user)) -> dict:
    """Kitchens see every request; an NGO sees only its own requests on each offer; signed out, offers without requests."""
    ngo_id = user["id"] if user and user["role"] == "ngo" else (None if user else "nobody")
    return {"offers": donations.offers(status, ngo_id), "stats": donations.stats(),
            "handover_hours": knowledge.rule_value("handover_hours", donations.DEFAULT_HANDOVER_HOURS),
            "rules": [r for r in knowledge.rules() if r["key"] in ("handover_hours", "hot_holding_c", "cold_holding_c", "min_donation_portions")]}


@router.get("/donations/suggest")
def suggest(date: Date, slot: Slot, source: str = Query("log", pattern="^(log|plan)$"), _: dict = Depends(kitchen_user),
            svc: ForecastService = Depends(get_service)) -> dict:
    """Dishes and portions to offer: what the Daily log says was left over, or what the approved plan is expected to
    leave (approved minus the most likely demand)."""
    check_date(date)
    names = svc.dishes.set_index("dish_id")["dish_name"]
    if source == "log":
        kit = get_store().read("kitchen_log")
        kit = kit[(kit["date"] == str(date)) & (kit["meal_slot"] == slot)]
        items = [{"dish_id": r["dish_id"], "dish_name": names.get(r["dish_id"], r["dish_id"]), "portions": int(float(r["leftover_qty"] or 0))}
                 for _, r in kit.iterrows()]
        note = "From the Daily log: the portions left over." if len(kit) else "Nothing is logged for this meal yet. Log the day first, or use the expected surplus of the plan."
    else:
        review = latest_review(str(date), slot)
        approved = review and review["decision"] == "approve"
        plan = svc.forecast(date, slot, overrides=Overrides(**(review.get("overrides", {}) if approved else {})))
        wanted = {d["dish_id"]: d["p50"] for d in plan["dishes"]}
        if approved:
            cooked = review["approved"]
            note = "Expected surplus: the approved quantity minus the most likely demand. Check what is really left before you post."
        else:   # not approved yet: what the kitchen cooks anyway (its usual plan, or the recommendation for a new dish)
            cooked = {d["dish_id"]: d["usual_plan"] or d["recommended"] for d in plan["dishes"]}
            note = ("This plan is not approved yet, so this is what is left if the kitchen cooks its usual amount: the usual plan "
                    "minus the most likely demand. Approve the plan for a closer figure.")
        items = [{"dish_id": d, "dish_name": names.get(d, d), "portions": int(q - wanted.get(d, q))} for d, q in cooked.items()]
    items = sorted([i for i in items if i["portions"] > 0], key=lambda i: -i["portions"])
    return {"items": items, "note": note, "total": sum(i["portions"] for i in items)}


@router.post("/donations")
def create(body: OfferIn, user: dict = Depends(kitchen_user)) -> dict:
    try:
        to = None
        if body.to_ngo_id:
            to = next((a for a in accounts.list_accounts("ngo") if a["id"] == body.to_ngo_id), None)
            if to is None:
                raise donations.DonationError("That NGO was not found. Choose another one.")
        offer = donations.create_offer(user, str(body.date), body.meal_slot, body.items, body.pickup_until, body.location,
                                       body.notes, knowledge.rule_value("handover_hours"), to)
    except (donations.DonationError, KeyError, TypeError, ValueError) as exc:
        raise _bad(exc if isinstance(exc, ValueError) else ValueError("Each dish needs a number of portions.")) from exc
    who = f" to {offer['to_ngo']['org_name']}" if offer.get("to_ngo") else " to every approved NGO"
    return {"offer": offer, "message": f"Sent {offer['total_portions']:,} portions{who}, to collect by {offer['pickup_until'].replace('T', ' ')}."}


@router.post("/donations/{offer_id}/claim")
def request_food(offer_id: str, body: ClaimIn, user: dict = Depends(current_user)) -> dict:
    try:
        offer = donations.claim(offer_id, user, body.portions, body.pickup_at, body.note)
    except donations.DonationError as exc:
        raise _bad(exc) from exc
    return {"offer": offer, "message": f"Requested {body.portions:,} portions from {offer['kitchen_name']}. The kitchen will accept it here."}


@router.post("/donations/{offer_id}/claims/{claim_id}")
def act(offer_id: str, claim_id: str, body: ClaimActionIn, user: dict = Depends(current_user)) -> dict:
    try:
        offer = donations.act_on_claim(offer_id, claim_id, body.action, user)
    except donations.DonationError as exc:
        raise _bad(exc) from exc
    words = {"accept": "Request accepted.", "decline": "Request declined." if user["role"] == "kitchen" else "Request withdrawn.",
             "collected": "Marked as collected. Thank you for passing the food on."}
    return {"offer": offer, "message": words[body.action]}


@router.post("/donations/{offer_id}/cancel")
def cancel(offer_id: str, user: dict = Depends(kitchen_user)) -> dict:
    try:
        offer = donations.cancel(offer_id, user)
    except donations.DonationError as exc:
        raise _bad(exc) from exc
    return {"offer": offer, "message": "Offer cancelled. Any open requests were declined."}

