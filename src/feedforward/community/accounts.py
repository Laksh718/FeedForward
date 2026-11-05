"""Accounts for the two kinds of organisation that use FeedForward together.

- kitchen: a mess, hostel or kitchen that plans meals and offers its surplus food. Creating one needs the invite code
  (ADMIN_PIN), so strangers cannot sign up as a kitchen. A kitchen account also unlocks the Daily log without the PIN,
  uploads documents and approves NGO accounts.
- ngo: an NGO, food bank or help group that collects surplus food. Anyone can register one; it starts "pending" and
  can request food once a kitchen account has approved it.

Passwords are stored as salted PBKDF2-SHA256 hashes (Python standard library), never in plain text. A sign in returns a
random session token (kept for 14 days) that the dashboard sends as "Authorization: Bearer <token>".
Files: accounts.json in the admin log folder, sessions in a private subfolder (so signing in does not count as a change
that makes open dashboards reload, see feedforward.admin.activity.version).
"""

import hashlib
import hmac
import json
import re
import secrets
import threading
from datetime import datetime, timedelta

from feedforward import config as C

ROLES = ("kitchen", "ngo")
STATUSES = ("active", "pending", "disabled")
SESSION_DAYS = 14
PBKDF2_ROUNDS = 240_000
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_lock = threading.RLock()


class AccountError(ValueError):
    """A request about accounts that cannot be done, with a message for the person."""


def _accounts_path():
    return C.ADMIN_LOG_DIR / "accounts.json"


def _sessions_path():
    return C.ADMIN_LOG_DIR / "private" / "sessions.json"


def _read(path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write(path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    tmp.replace(path)


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ROUNDS).hex()
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt}${digest}"


def check_password(password: str, stored: str) -> bool:
    try:
        _, rounds, salt, digest = stored.split("$")
    except ValueError:
        return False
    test = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds)).hex()
    return hmac.compare_digest(test, digest)


def public(user: dict) -> dict:
    """An account without its password hash."""
    return {k: v for k, v in user.items() if k != "password"}


def register(email: str, password: str, name: str, org_name: str, role: str, invite_code: str | None = None,
             admin_pin: str = "", phone: str = "", area: str = "", capacity: int | None = None) -> dict:
    """Create an account. Kitchen accounts need the invite code; NGO accounts start pending."""
    email = email.strip().lower()
    if role not in ROLES:
        raise AccountError("Choose kitchen or NGO.")
    if not EMAIL.match(email):
        raise AccountError("Enter a valid email address.")
    if len(password) < 8:
        raise AccountError("Use a password of at least 8 characters.")
    if not name.strip() or not org_name.strip():
        raise AccountError("Give your name and the name of your kitchen or organisation.")
    if role == "kitchen":
        if not admin_pin or admin_pin == "change-me":
            raise AccountError("Kitchen accounts are switched off until ADMIN_PIN is set on the server.")
        if not invite_code or not secrets.compare_digest(invite_code.encode(), admin_pin.encode()):
            raise AccountError("The invite code is not correct. Kitchen accounts need the code from the kitchen's administrator.")
    with _lock:
        accounts = _read(_accounts_path())
        if any(a["email"] == email for a in accounts.values()):
            raise AccountError("An account with this email already exists. Sign in instead.")
        uid = secrets.token_hex(6)
        user = {"id": uid, "email": email, "password": hash_password(password), "name": name.strip()[:80],
                "org_name": org_name.strip()[:120], "role": role, "status": "active" if role == "kitchen" else "pending",
                "phone": phone.strip()[:40], "area": area.strip()[:120], "capacity": capacity,
                "created_at": datetime.now().isoformat(timespec="seconds"), "approved_by": None}
        accounts[uid] = user
        _write(_accounts_path(), accounts)
    return public(user)


def login(email: str, password: str) -> tuple[str, dict]:
    """Check the password and start a session. Returns (token, account)."""
    email = email.strip().lower()
    with _lock:
        user = next((a for a in _read(_accounts_path()).values() if a["email"] == email), None)
        if user is None or not check_password(password, user["password"]):
            raise AccountError("The email or the password is not correct.")
        if user["status"] == "disabled":
            raise AccountError("This account has been switched off by a kitchen administrator.")
        sessions = _read(_sessions_path())
        now = datetime.now()
        sessions = {t: s for t, s in sessions.items() if s["expires"] > now.isoformat()}   # forget expired ones
        token = secrets.token_urlsafe(32)
        sessions[token] = {"user_id": user["id"], "expires": (now + timedelta(days=SESSION_DAYS)).isoformat(timespec="seconds")}
        _write(_sessions_path(), sessions)
    return token, public(user)


def logout(token: str) -> None:
    with _lock:
        sessions = _read(_sessions_path())
        if sessions.pop(token, None) is not None:
            _write(_sessions_path(), sessions)


def user_for(token: str | None) -> dict | None:
    """The account of a session token, or None (no token, unknown, expired or the account switched off)."""
    if not token:
        return None
    s = _read(_sessions_path()).get(token)
    if not s or s["expires"] < datetime.now().isoformat():
        return None
    user = _read(_accounts_path()).get(s["user_id"])
    return public(user) if user and user["status"] != "disabled" else None


def list_accounts(role: str | None = None) -> list[dict]:
    accounts = [public(a) for a in _read(_accounts_path()).values() if role is None or a["role"] == role]
    return sorted(accounts, key=lambda a: (a["status"] != "pending", a["org_name"].lower()))


def set_status(account_id: str, status: str, by: dict) -> dict:
    """A kitchen account approves (active) or switches off (disabled) an NGO account."""
    if status not in STATUSES:
        raise AccountError(f"Status must be one of {list(STATUSES)}.")
    with _lock:
        accounts = _read(_accounts_path())
        user = accounts.get(account_id)
        if user is None:
            raise AccountError("No such account.")
        if user["role"] != "ngo":
            raise AccountError("Only NGO accounts are approved here.")
        user["status"] = status
        user["approved_by"] = by["org_name"] if status == "active" else user.get("approved_by")
        _write(_accounts_path(), accounts)
    return public(user)
