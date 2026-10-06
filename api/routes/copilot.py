"""POST /api/chat: explain the forecast. The copilot only explains; it never changes or approves anything."""

from datetime import date as Date
from datetime import timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api import services
from api.deps import get_service
from api.schemas import OverridesIn, Scope, Slot
from feedforward.copilot.explain import answer_question
from feedforward.models.forecast_service import ForecastService

router = APIRouter()


class ChatIn(BaseModel):
    """A question and what the page is showing, so words like "this dish" or "tomorrow" have a meaning."""

    question: str = Field(min_length=2, max_length=500)
    date: Date | None = None
    meal_slot: Slot = "lunch"
    scope: Scope = "core"
    overrides: OverridesIn = OverridesIn()


@router.post("/chat")
def chat(body: ChatIn, svc: ForecastService = Depends(get_service)) -> dict:
    """One answer: the text, whether it came from the language model or the template, and the figures it used."""
    today = services.today()
    return answer_question(body.question, svc, body.date or today + timedelta(days=1), body.meal_slot, body.scope,
                           body.overrides.to_domain(), today)
