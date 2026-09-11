"""
Server-rendered dashboard (spec section 6). Routes call document_service
directly and pass real data into Jinja2 templates - the upload form is a
plain HTML POST, and errors/success are shown via Bootstrap toasts driven
by Flask's flash-message system across a redirect.

The REST API (api/routes/documents.py) is untouched and still the real
JSON contract the spec requires and still keyed by the real document
name - this blueprint additionally exposes clean, readable URL slugs
(e.g. /document/consolidated-cash-flow-statement-2018 instead of a raw,
percent-encoded filename) purely as a cosmetic routing layer on top of
the same document_service functions the API uses.
"""
import re
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


def _slugify(document_name: str) -> str:
    """
    Turns a raw filename like "Consolidated Cash Flow Statement 2018.pdf"
    into a clean URL slug like "consolidated-cash-flow-statement-2018" -
    lowercase, hyphen-separated, no extension, no spaces/percent-encoding.
    """
    stem = Path(document_name).stem  # drops the file extension
    slug = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    return slug or "document"


def _build_slug_map() -> dict:
    """
    Maps slug -> real document_name for every processed document, computed
    fresh each request from the (small) processed-documents list. Good
    enough for this dataset's scale; a production version with many
    documents would persist the slug alongside the record instead of
    recomputing it - see README known limitations.
    """
    documents = document_service.list_documents()
    slug_map = {}
    for doc in documents:
        slug_map[_slugify(doc["document_name"])] = doc["document_name"]
    return slug_map, documents


@frontend_bp.route("/", methods=["GET"])
def dashboard():
    slug_map, documents = _build_slug_map()
    for doc in documents:
        doc["slug"] = _slugify(doc["document_name"])
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
    return redirect(url_for("frontend.document_result", slug=_slugify(result["document_name"])))


@frontend_bp.route("/document/<string:slug>")
def document_result(slug):
    slug_map, _ = _build_slug_map()
    document_name = slug_map.get(slug)

    if document_name is None:
        flash(f'No processed result found for "{slug}".', "warning")
        return redirect(url_for("frontend.dashboard"))

    result = document_service.get_by_name(document_name)
    if result is None:
        flash(f'No processed result found for "{document_name}".', "warning")
        return redirect(url_for("frontend.dashboard"))

    line_items = result.get("line_items") or []
    line_item_columns = []
    for item in line_items:
        for key in item.keys():
            if key not in line_item_columns:
                line_item_columns.append(key)

    return render_template(
        "document_result.html",
        result=result,
        line_item_columns=line_item_columns,
    )
