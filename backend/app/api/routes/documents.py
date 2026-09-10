"""
REST API routes (spec section 5). Thin controllers only - all real
work happens in app.services.document_service. Uses flask-smorest so
Swagger/OpenAPI docs are generated automatically and served at /docs.
"""
from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint

from app.core.logging import get_logger
from app.services import document_service
from app.utils.exceptions import DocumentNotFoundError, MissingFileError

logger = get_logger(__name__)

documents_bp = Blueprint(
    "documents", __name__, url_prefix="/api/v1", description="Document processing endpoints"
)


@documents_bp.route("/health")
class Health(MethodView):
    def get(self):
        """Health check for the deployed service."""
        return {"status": "ok"}, 200


@documents_bp.route("/documents/process")
class ProcessDocument(MethodView):
    def post(self):
        """Upload and process a PDF / JPG / PNG document."""
        if "file" not in request.files:
            raise MissingFileError("No file part in the request.")
        uploaded = request.files["file"]
        if uploaded.filename == "":
            raise MissingFileError("No file selected.")

        document_type = request.form.get("document_type", "")
        file_bytes = uploaded.read()

        result = document_service.process_document(uploaded.filename, file_bytes, document_type)
        return result, 200


@documents_bp.route("/documents/<string:document_name>")
class GetDocument(MethodView):
    def get(self, document_name):
        """Retrieve the latest structured result for a document by name."""
        result = document_service.get_by_name(document_name)
        if result is None:
            raise DocumentNotFoundError(f"No processed result found for '{document_name}'.")
        return result, 200


@documents_bp.route("/documents")
class ListDocuments(MethodView):
    def get(self):
        """List processed documents for the frontend dashboard."""
        return {"documents": document_service.list_documents()}, 200
