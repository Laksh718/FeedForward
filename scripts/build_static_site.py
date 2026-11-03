"""Build the static online demo of the dashboard (for GitHub Pages) from the trained model.

The dashboard in app/ normally talks to the FastAPI server, but GitHub Pages only serves files. This script
calls the real API in process (same code, same model, same numbers), saves every answer the dashboard can ask
for as JSON under <out>/data/, and copies app/ next to it with a marker that switches the page into static
mode (app/js/static-api.js reads the snapshot instead of calling /api).

Run from the project root, after the pipeline has produced artifacts/ (see the README):
    python scripts/build_static_site.py              # writes site/
    python scripts/build_static_site.py --out DIR
    python scripts/build_static_site.py --api-url ""   # snapshot only, no deployed server behind the page

What the snapshot holds:
- health, and for every date the calendar covers: the plan (main dishes and all dishes) and the menu of each slot
- the week chart from the default plan date: totals per slot, and per dish for every dish on that slot's menu
- every calendar month
- for the 7 days from the default plan date: what if (one setting at a time) and the copilot's suggested questions

Local Daily log entries and reviews never go into the build (it uses an empty admin log folder), and the copilot
uses its template wording (no language model key), so the snapshot is deterministic and safe to publish.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import date as Date
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

# Set before the app is imported: config reads the admin folder at import time, and load_dotenv never
# overrides a variable that is already set (even to an empty value).
os.environ["FEEDFORWARD_ADMIN_LOG_DIR"] = tempfile.mkdtemp(prefix="feedforward-static-")
os.environ["GEMINI_API_KEY"] = ""
os.environ["GROQ_API_KEY"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from api.main import app  # noqa: E402
from feedforward import config as C  # noqa: E402
from feedforward.data.weather_types import WEATHER_TYPE_RAIN_LEVEL  # noqa: E402

APP_DIR = ROOT / "app"
SCOPES = ("core", "all")
WINDOW_DAYS = 7                                               # what if and copilot answers cover this many days
ATTENDANCE_STEPS = [p for p in range(-30, 31, 5) if p != 0]   # the what if slider in app/js/whatif.js
SPECIAL_DAYS = ("special_day", "exam_week", "festival")
STATIC_MARKER = '<meta name="feedforward-mode" content="static">'
# The deployed server (Render) that answers what the snapshot cannot: combined what ifs, other dates, free copilot
# questions, approvals and the Daily log. Its CORS_ORIGINS must include the site's address (https://laksh718.github.io).
DEFAULT_API_URL = os.getenv("FEEDFORWARD_API_URL", "https://feedforward-195t.onrender.com")

client = TestClient(app)


def call(method: str, path: str, **kwargs) -> dict:
    """One API call; any non 200 answer stops the build with the server's message."""
    r = client.request(method, f"/api{path}", **kwargs)
    if r.status_code != 200:
        raise SystemExit(f"{method} {path} {kwargs} failed with {r.status_code}: {r.text[:400]}")
    return r.json()


def write(out: Path, rel: str, obj) -> None:
    path = out / "data" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def js_value(v) -> str:
    """How JavaScript turns the value into text in a template string (true, 10, Light Rain)."""
    return "true" if v is True else "false" if v is False else str(v)


def overrides_key(o: dict) -> str:
    """Must match overridesKey in app/js/static-api.js."""
    return "&".join(f"{k}={js_value(v)}" for k, v in sorted(o.items()))


def single_overrides() -> list[dict]:
    """Every what if the controls can send with one setting changed."""
    return ([{"attendance_change_pct": p} for p in ATTENDANCE_STEPS] + [{s: True} for s in SPECIAL_DAYS]
            + [{"weather_type": w} for w in WEATHER_TYPE_RAIN_LEVEL])


def chip_questions() -> list[str]:
    """The suggested questions of both views, read from the page code so they never drift apart."""
    out = []
    for name in ("service.js", "desk.js"):
        m = re.search(r"^const CHIPS = (\[.*?\]);", (APP_DIR / "js" / name).read_text(encoding="utf-8"), re.M)
        if not m:
            raise SystemExit(f"Could not find the CHIPS list in app/js/{name}")
        out += [q for q in json.loads(m.group(1)) if q not in out]
    return out


def days_between(first: Date, last: Date) -> list[Date]:
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]


def months_between(first: Date, last: Date) -> list[str]:
    out, y, m = [], first.year, first.month
    while (y, m) <= (last.year, last.month):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def source_commit() -> str:
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        return sha + ("-dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def progress(label: str, done: int, total: int, started: float) -> None:
    if done == total or done % 25 == 0:
        print(f"\r  {label}: {done}/{total} ({time.time() - started:.0f}s)", end="\n" if done == total else "", flush=True)


def write_page(out: Path, api_url: str = DEFAULT_API_URL) -> None:
    """Fresh copy of app/ with the static marker (and the deployed server's address); keeps out/data/ when it is there."""
    data = out / "data"
    kept = Path(tempfile.mkdtemp(prefix="feedforward-data-")) / "data" if data.exists() else None
    if kept:
        shutil.move(data, kept)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(APP_DIR, out)
    if kept:
        shutil.move(kept, data)
    index = out / "index.html"
    html = index.read_text(encoding="utf-8")
    if '<meta charset="utf-8">' not in html:
        raise SystemExit("app/index.html has no <meta charset=\"utf-8\"> to put the static marker after")
    marker = STATIC_MARKER + (f'\n  <meta name="feedforward-api" content="{api_url.rstrip("/")}">' if api_url else "")
    index.write_text(html.replace('<meta charset="utf-8">', f'<meta charset="utf-8">\n  {marker}', 1), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")   # serve the files as they are, no Jekyll step


def refresh_page(out: Path, api_url: str = DEFAULT_API_URL) -> None:
    """Page only: new app/ files, same snapshot. Only valid while the Python code and artifacts/ are unchanged."""
    write_page(out, api_url)
    path = out / "data" / "health.json"
    health = json.loads(path.read_text(encoding="utf-8"))
    health["demo"]["source_commit"] = source_commit()
    path.write_text(json.dumps(health, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Refreshed the page files in {out}; kept the snapshot from {health['demo']['built_at']}.")


def build(out: Path, api_url: str = DEFAULT_API_URL) -> None:
    started = time.time()
    if out.exists():
        shutil.rmtree(out)
    write_page(out, api_url)

    health = call("GET", "/health")
    first, last = Date.fromisoformat(C.HISTORY_START), Date.fromisoformat(C.FORECAST_LAST_DAY)
    week_start = Date.fromisoformat(health["default_plan_date"])
    window = [d for d in days_between(week_start, week_start + timedelta(days=WINDOW_DAYS - 1)) if d <= last]
    questions = chip_questions()

    print("Plans and menus for every date and slot")
    dates, menu_ids, t = days_between(first, last), {s: set() for s in C.MEAL_SLOTS}, time.time()
    for i, d in enumerate(dates, 1):
        bundle = {"plans": {}, "menu": {}}
        for slot in C.MEAL_SLOTS:
            bundle["plans"][slot] = {sc: call("GET", "/plan", params={"date": str(d), "slot": slot, "scope": sc}) for sc in SCOPES}
            bundle["menu"][slot] = call("GET", "/dishes", params={"date": str(d), "slot": slot})
            menu_ids[slot].update(x["dish_id"] for x in bundle["menu"][slot]["dishes"])
        write(out, f"days/{d}.json", bundle)
        progress("days", i, len(dates), t)

    print(f"Week from {week_start}: totals and every dish on each slot's menu")
    jobs = [(slot, sc, None) for slot in C.MEAL_SLOTS for sc in SCOPES] + \
           [(slot, None, dish) for slot in C.MEAL_SLOTS for dish in sorted(menu_ids[slot])]
    t = time.time()
    for i, (slot, sc, dish) in enumerate(jobs, 1):
        params = {"slot": slot, "start": str(week_start)} | ({"dish_id": dish} if dish else {"scope": sc})
        write(out, f"week/{slot}/dish/{dish}.json" if dish else f"week/{slot}/{sc}.json", call("GET", "/week", params=params))
        progress("week views", i, len(jobs), t)

    print("Calendar months")
    months = months_between(first, last)
    for m in months:
        write(out, f"calendar/{m}.json", call("GET", "/calendar", params={"month": m}))
    print(f"  {len(months)} months")

    print(f"What if, one setting at a time, {window[0]} to {window[-1]}")
    singles, t = single_overrides(), time.time()
    total, n = len(window) * len(C.MEAL_SLOTS) * len(SCOPES) * len(singles), 0
    for d in window:
        answers = {}
        for slot in C.MEAL_SLOTS:
            answers[slot] = {}
            for sc in SCOPES:
                answers[slot][sc] = {}
                for o in singles:
                    body = {"date": str(d), "meal_slot": slot, "scope": sc, "overrides": o}
                    answers[slot][sc][overrides_key(o)] = call("POST", "/whatif", json=body)
                    n += 1
                    progress("what if", n, total, t)
        write(out, f"whatif/{d}.json", answers)

    print(f"Copilot answers to the suggested questions, {window[0]} to {window[-1]}")
    t, total, n = time.time(), len(window) * len(C.MEAL_SLOTS) * len(SCOPES) * len(questions), 0
    for d in window:
        answers = {}
        for slot in C.MEAL_SLOTS:
            answers[slot] = {}
            for sc in SCOPES:
                answers[slot][sc] = {}
                for q in questions:
                    r = call("POST", "/chat", json={"question": q, "date": str(d), "meal_slot": slot, "scope": sc})
                    answers[slot][sc][q] = {"answer": r["answer"], "source": r["source"], "intent": r.get("intent")}
                    n += 1
                    progress("answers", n, total, t)
        write(out, f"chat/{d}.json", answers)

    health["demo"] = {
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "source_commit": source_commit(),
        "first_date": str(first), "last_date": str(last), "week_start": str(week_start),
        "whatif_dates": [str(d) for d in window], "chat_dates": [str(d) for d in window], "chat_questions": questions,
    }
    write(out, "health.json", health)

    files = [p for p in out.rglob("*") if p.is_file()]
    size = sum(p.stat().st_size for p in files) / 1e6
    print(f"Done in {time.time() - started:.0f}s: {len(files)} files, {size:.1f} MB in {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "site", help="output folder (default: site/)")
    parser.add_argument("--reuse-data", action="store_true",
                        help="only refresh the page files (app/ changed, the Python code and model did not); takes seconds")
    parser.add_argument("--api-url", default=DEFAULT_API_URL,
                        help=f"deployed FeedForward server the page may call (default {DEFAULT_API_URL}; empty for snapshot only)")
    args = parser.parse_args()
    out = args.out.resolve()
    # The output folder is deleted and rebuilt, so only ever replace an empty folder or an earlier build.
    if out == ROOT or out in ROOT.parents or (out.exists() and any(out.iterdir()) and not (out / "data" / "health.json").exists()):
        raise SystemExit(f"Refusing to replace {out}: it is not empty and not an earlier build. Choose another --out.")
    if args.reuse_data:
        if not (out / "data" / "health.json").exists():
            raise SystemExit(f"--reuse-data needs an earlier build in {out}. Run once without it.")
        return refresh_page(out, args.api_url)
    if not (C.MODELS_DIR / "final").exists():
        raise SystemExit("No trained model in artifacts/models/final. Run the pipeline first (see the README).")
    build(out, args.api_url)


if __name__ == "__main__":
    main()
