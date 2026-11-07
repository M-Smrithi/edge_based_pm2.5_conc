"""Flask application factory."""
from __future__ import annotations
import os, secrets
from datetime import timedelta
from pathlib import Path

from flask import Flask, jsonify, render_template, request

import core.config as C


def _secret() -> str:
    env = os.environ.get("SECRET_KEY")
    if env and len(env) >= 24 and env != "change-me-to-a-long-random-string":
        return env
    p = Path(C.INSTANCE) / "secret.key"
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text(secrets.token_hex(32)); os.chmod(p, 0o600)
    return p.read_text().strip()


def create_app(overrides: dict | None = None) -> Flask:
    if os.environ.get("AIOT_HOME"):
        C.set_home(os.environ["AIOT_HOME"])
    if overrides and overrides.get("AIOT_HOME"):
        C.set_home(overrides["AIOT_HOME"])
    C.ensure_dirs()
    app = Flask(__name__, template_folder=str(C.ROOT / "templates"), static_folder=str(C.ROOT / "static"))
    app.config.update(
        SECRET_KEY=_secret(), MAX_CONTENT_LENGTH=C.MAX_REQUEST_BYTES, JSON_SORT_KEYS=False,
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("AIOT_SECURE_COOKIES", "0") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=C.SESSION_HOURS), TESTING=False)
    if overrides:
        app.config.update({k: v for k, v in overrides.items() if k != "AIOT_HOME"})

    from app import db, security
    con = db.connect(); db.migrate(con); con.close()
    app.teardown_appcontext(db.close_db)
    app.before_request(security.load_user)
    app.before_request(security.check_csrf)
    app.after_request(security.add_headers)

    from app.api_public import bp as public_api
    from app.api_admin import bp as admin_api
    from app.pages import bp as pages
    app.register_blueprint(public_api); app.register_blueprint(admin_api); app.register_blueprint(pages)

    @app.errorhandler(Exception)
    def _err(e):
        from werkzeug.exceptions import HTTPException
        code = e.code if isinstance(e, HTTPException) else 500
        msg = (e.description if isinstance(e, HTTPException) else "Internal server error.")
        if code == 500:
            app.logger.exception("unhandled error")
        if request.path.startswith("/api/"):
            return jsonify(error=msg), code
        return render_template("error.html", code=code, message=msg), code

    @app.context_processor
    def _ctx():
        from flask import g
        return dict(csrf=security.csrf_token(), user=getattr(g, "user", None))
    return app
