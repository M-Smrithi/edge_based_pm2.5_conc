"""HTML pages. Admin pages redirect unauthenticated visitors to the login page; data always comes from the JSON API."""
from __future__ import annotations
from flask import Blueprint, g, redirect, render_template, url_for

bp = Blueprint("pages", __name__)

PUBLIC = {"": ("index.html", "Overview"), "air-quality": ("air_quality.html", "Air quality"), "predict": ("predict.html", "Prediction Studio"),
          "research": ("research.html", "Research Lab"), "methodology": ("methodology.html", "Methodology")}
ADMIN = {"": ("overview.html", "Overview"), "datasets": ("datasets.html", "Dataset Manager"), "training": ("training.html", "Model Training Center"),
         "experiments": ("experiments.html", "Experiment Manager"), "models": ("models.html", "Model Registry"), "audit": ("audit.html", "Audit Log"),
         "settings": ("settings.html", "Settings")}


def _pub(key):
    def view(): return render_template("public/" + PUBLIC[key][0], title=PUBLIC[key][1], page=key or "home")
    view.__name__ = "pub_" + (key or "home"); return view


for _k in PUBLIC:
    bp.add_url_rule("/" + _k, view_func=_pub(_k))


@bp.route("/admin/login")
def admin_login():
    if g.user: return redirect(url_for("pages.admin_" + "home"))
    return render_template("admin/login.html", title="Sign in")


def _adm(key):
    def view():
        if not g.user: return redirect("/admin/login")
        return render_template("admin/" + ADMIN[key][0], title=ADMIN[key][1], page=key or "overview")
    view.__name__ = "admin_" + (key or "home"); return view


for _k in ADMIN:
    bp.add_url_rule("/admin/" + _k if _k else "/admin", view_func=_adm(_k), strict_slashes=False)
