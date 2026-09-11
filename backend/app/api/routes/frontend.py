"""
Server-rendered dashboard (spec section 6). Unlike a typical SPA, these
routes call document_service directly and pass real data into Jinja2
templates - the upload form is a plain HTML POST (no JavaScript fetch),
and errors are shown via Flask's flash-message system across a redirect.

The REST API (api/routes/documents.py) is untouched and still the real
JSON contract the spec requires - this blueprint is purely the human-
facing convenience layer on top of the same document_service functions
the API uses.
"""
from pathlib import Path

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.core.logging import get_logger
from app.services import document_service
from app.utils.exceptions import AppError

logger = get_logger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_FRONTEND_DIR = _PROJECT_ROOT / "frontend"

frontend_bp = Blueprint(
    "frontend", __name__,
    template_folder=str(_FRONTEND_DIR / "templates"),
    static_folder=str(_FRONTEND_DIR / "static"),
    static_url_path="/static",
)


@frontend_bp.route("/", methods=["GET"])
def dashboard():
    documents = document_service.list_documents()
    return render_template("dashboard.html", documents=documents)


@frontend_bp.route("/", methods=["POST"])
def process_upload():
    uploaded = request.files.get("file")
    document_type = request.form.get("document_type", "")

    if uploaded is None or uploaded.filename == "":
        flash("Please choose a file before submitting.", "danger")
        return redirect(url_for("frontend.dashboard"))

    file_bytes = uploaded.read()

    try:
        result = document_service.process_document(uploaded.filename, file_bytes, document_type)
    except AppError as exc:
        logger.warning("Upload rejected: %s - %s", exc.code, exc.message)
        flash(f"{exc.message}", "danger")
        return redirect(url_for("frontend.dashboard"))

    flash(f'"{result["document_name"]}" processed - status: {result["processing_status"]}', "success")
    return redirect(url_for("frontend.document_result", document_name=result["document_name"]))


@frontend_bp.route("/document/<string:document_name>")
def document_result(document_name):
    result = document_service.get_by_name(document_name)
    if result is None:
        flash(f'No processed result found for "{document_name}".', "warning")
        return redirect(url_for("frontend.dashboard"))
    return render_template("document_result.html", result=result)
