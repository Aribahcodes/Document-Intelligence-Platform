"""
Frontend page-shell routes (spec section 6). Unlike the earlier
server-rendered iteration, these routes do NOT call document_service
directly - per spec section 6 ("Frontend must call the deployed
backend/API"), all real data (the processed-document list, upload
processing, and individual results) is fetched client-side via
JavaScript against the actual REST API in api/routes/documents.py.

This file's only remaining job is serving the page shells themselves
(the HTML template + static assets) - genuinely just routing, no
business logic, no persistence access.
"""
from pathlib import Path

from flask import Blueprint, render_template

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


@frontend_bp.route("/document/<string:slug>")
def document_result(slug):
    return render_template("document_result.html", slug=slug)
