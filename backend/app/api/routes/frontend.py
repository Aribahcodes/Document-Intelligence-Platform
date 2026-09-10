"""
Serves the HTML/CSS/JS dashboard (spec section 6). Pages are static
shells - all data comes from the REST API via client-side fetch calls,
so this blueprint has no business logic of its own.
"""
from pathlib import Path

from flask import Blueprint, render_template

# backend/app/api/routes/frontend.py -> project-root/frontend/{templates,static}
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_FRONTEND_DIR = _PROJECT_ROOT / "frontend"

frontend_bp = Blueprint(
    "frontend", __name__,
    template_folder=str(_FRONTEND_DIR / "templates"),
    static_folder=str(_FRONTEND_DIR / "static"),
    static_url_path="/static",
)


@frontend_bp.route("/")
def dashboard():
    return render_template("dashboard.html")


@frontend_bp.route("/document/<string:document_name>")
def document_result(document_name):
    return render_template("document_result.html", document_name=document_name)
