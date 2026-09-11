"""
Central application configuration.

All secrets and environment-specific values are read from environment
variables (see .env.example). Nothing sensitive is hardcoded here.
"""
import os
from pathlib import Path


class Config:
    ENV = os.getenv("APP_ENV", "development")
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-me")

    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    DEFAULT_DB_PATH = BASE_DIR / "data" / "app.db"
    DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{DEFAULT_DB_PATH}"

    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    TESSERACT_CMD = os.getenv("TESSERACT_CMD")
    OCR_TEXT_MIN_CHARS = int(os.getenv("OCR_TEXT_MIN_CHARS", "30"))

    MAX_UPLOAD_SIZE_BYTES = int(os.getenv("MAX_UPLOAD_SIZE_BYTES", str(15 * 1024 * 1024)))
    MAX_PAGE_COUNT = int(os.getenv("MAX_PAGE_COUNT", "3"))
    ALLOWED_MIME_TYPES = {"application/pdf", "image/jpeg", "image/png"}
    UPLOAD_DIR = BASE_DIR / "data" / "uploads"

    VALIDATION_TOLERANCE = float(os.getenv("VALIDATION_TOLERANCE", "0.01"))

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_DIR = BASE_DIR / "data" / "logs"


def init_dirs():
    Config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    Config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    Config.DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
