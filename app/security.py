"""Authentication, role authorisation, CSRF, lockout, password policy, audit helper, security headers."""
from __future__ import annotations
import json, re, secrets
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import abort, g, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

import core.config as C
from app.db import get_db

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")
_DUMMY = generate_password_hash("dummy-password-for-timing")


def now() -> datetime: return datetime.now(timezone.utc)
def iso(dt: datetime | None = None) -> str: return (dt or now()).isoformat(timespec="seconds")


def hash_password(pw: str) -> str:
    return generate_password_hash(pw, method="scrypt")


def password_problems(pw: str, email: str = "") -> list[str]:
    out = []
    if len(pw) < C.MIN_PASSWORD_LEN: out.append(f"at least {C.MIN_PASSWORD_LEN} characters")
    if not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw): out.append("a mix of letters and digits")
    if email and email.split("@")[0].lower() in pw.lower(): out.append("must not contain your email name")
    return out


def create_user(email: str, password: str, role: str = "admin", name: str = "") -> int:
    email = email.strip().lower()
    if not EMAIL_RE.match(email): raise ValueError("invalid email address")
    if role not in ("admin", "analyst"): raise ValueError("invalid role")
    p = password_problems(password, email)
    if p: raise ValueError("Password needs: " + ", ".join(p))
    db = get_db() if g else None
    from app.db import connect
    con = db or connect()
    cur = con.execute("INSERT INTO users(email,name,password_hash,role,created_utc) VALUES(?,?,?,?,?)",
                      (email, name.strip()[:80], hash_password(password), role, iso()))
    return cur.lastrowid


# ---- audit ---------------------------------------------------------------------
def audit(action: str, target: str | None = None, detail: dict | None = None, user=None, con=None):
    con = con or get_db()
    try:
        u = user if user is not None else getattr(g, "user", None)
    except RuntimeError:
        u = user
    try:
        ip = request.remote_addr
    except RuntimeError:
        ip = None
    con.execute("INSERT INTO audit_log(ts,user_id,user_email,action,target,detail,ip) VALUES(?,?,?,?,?,?,?)",
                (iso(), u["id"] if u else None, u["email"] if u else None, action, target,
                 json.dumps(detail, default=str) if detail is not None else None, ip))


# ---- csrf ----------------------------------------------------------------------
def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def check_csrf():
    if request.method in UNSAFE and request.path.startswith("/api/"):
        sent = request.headers.get("X-CSRF-Token", "")
        if not sent or not secrets.compare_digest(sent, session.get("csrf", "")):
            abort(403, description="Missing or invalid CSRF token.")


# ---- session user ---------------------------------------------------------------
def load_user():
    g.user = None
    uid = session.get("uid")
    if uid:
        row = get_db().execute("SELECT * FROM users WHERE id=? AND active=1", (uid,)).fetchone()
        if row:
            g.user = row
        else:
            session.pop("uid", None)


def login(email: str, password: str):
    """Returns (user_row | None, message). Generic failure message; lockout after repeated failures."""
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE email=?", ((email or "").strip().lower(),)).fetchone()
    if row is None:
        check_password_hash(_DUMMY, password or "")
        return None, "Invalid email or password."
    if row["locked_until"] and row["locked_until"] > iso():
        return None, "Too many failed attempts. Try again later."
    if not row["active"] or not check_password_hash(row["password_hash"], password or ""):
        n = row["failed_logins"] + 1
        lock = iso(now() + timedelta(minutes=C.LOCKOUT_MINUTES)) if n >= C.MAX_FAILED_LOGINS else None
        db.execute("UPDATE users SET failed_logins=?, locked_until=? WHERE id=?", (0 if lock else n, lock, row["id"]))
        audit("login_failed", row["email"], {"locked": bool(lock)}, user={"id": row["id"], "email": row["email"]})
        return None, "Invalid email or password."
    db.execute("UPDATE users SET failed_logins=0, locked_until=NULL, last_login_utc=? WHERE id=?", (iso(), row["id"]))
    session.clear()
    session["uid"] = row["id"]; session.permanent = True; csrf_token()
    audit("login", row["email"], user={"id": row["id"], "email": row["email"]})
    return row, "ok"


def _deny(status, msg):
    r = jsonify(error=msg); r.status_code = status; return r


def admin_area(fn=None, *, write_role="admin"):
    """Decorator for admin API routes: authenticated user required; unsafe methods require the admin role."""
    def deco(f):
        @wraps(f)
        def inner(*a, **k):
            if g.user is None: return _deny(401, "Authentication required.")
            if request.method in UNSAFE and g.user["role"] != write_role: return _deny(403, "Your role cannot perform this action.")
            return f(*a, **k)
        return inner
    return deco(fn) if fn else deco


def add_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    resp.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    resp.headers.setdefault("Content-Security-Policy",
                            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
    if request.path.startswith("/api/") or request.path.startswith("/admin"):
        resp.headers["Cache-Control"] = "no-store"
    return resp
