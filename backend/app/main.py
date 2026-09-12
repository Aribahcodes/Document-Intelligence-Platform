"""
Application entry point / factory. Wires together config, logging,
database, the REST API (with Swagger docs at /docs), and the frontend
blueprint. Also installs a global error handler so every failure -
expected (AppError) or unexpected - returns the spec's error JSON
shape instead of a raw stack trace.
"""
from flask import Flask, jsonify
from flask_smorest import Api

from app.api.routes.documents import documents_bp
from app.api.routes.frontend import frontend_bp
from app.core.config import Config, init_dirs
from app.core.database import init_db
from app.core.logging import configure_logging, get_logger
from app.utils.exceptions import AppError


def create_app() -> Flask:
    init_dirs()

    configure_logging()
    logger = get_logger(__name__)

    init_db()

    # static files are served by frontend_bp (mapped to /static) instead of the
    # app's own default static folder, which we don't use - avoids a route collision.
    app = Flask(__name__, static_folder=None)
    app.config["SECRET_KEY"] = Config.SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = Config.MAX_UPLOAD_SIZE_BYTES

    # --- Swagger / OpenAPI setup ---
    app.config["API_TITLE"] = "Document Intelligence API"
    app.config["API_VERSION"] = "v1"
    app.config["OPENAPI_VERSION"] = "3.0.3"
    app.config["OPENAPI_URL_PREFIX"] = "/"
    app.config["OPENAPI_SWAGGER_UI_PATH"] = "/docs"
    app.config["OPENAPI_SWAGGER_UI_URL"] = "https://cdn.jsdelivr.net/npm/swagger-ui-dist/"

    api = Api(app)
    api.register_blueprint(documents_bp)
    app.register_blueprint(frontend_bp)

    _register_error_handlers(app, logger)

    logger.info("Application started (env=%s)", Config.ENV)
    return app


def _register_error_handlers(app: Flask, logger) -> None:
    @app.errorhandler(AppError)
    def handle_app_error(exc: AppError):
        logger.warning("Handled application error: %s - %s", exc.code, exc.message)
        return jsonify({"error": {"code": exc.code, "message": exc.message}}), exc.status_code

    @app.errorhandler(413)
    def handle_too_large(exc):
        return jsonify({"error": {
            "code": "FILE_TOO_LARGE",
            "message": "The uploaded file exceeds the maximum allowed size.",
        }}), 413

    @app.errorhandler(404)
    def handle_not_found(exc):
        return jsonify({"error": {"code": "NOT_FOUND", "message": "The requested resource was not found."}}), 404

    @app.errorhandler(Exception)
    def handle_unexpected(exc: Exception):
        # never leak stack traces / internals to the client
        logger.exception("Unhandled exception")
        return jsonify({"error": {
            "code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred while processing the request.",
        }}), 500


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=(Config.ENV == "development"), reloader_type="stat")
