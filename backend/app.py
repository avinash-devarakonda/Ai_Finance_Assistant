"""Flask application factory for Finora."""
from __future__ import annotations

import logging

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from config import Config, PROJECT_ROOT
from database import db
from routes.auth import auth_bp
from routes.budgets import budgets_bp
from routes.chatbot import chatbot_bp
from routes.dashboard import dashboard_bp
from routes.insights import insights_bp
from routes.ml import ml_bp
from routes.reports import reports_bp
from routes.transactions import transactions_bp
from services.classifier_service import model_info
from services.forecast_service import forecast_info
from utils.auth import authenticate_request
from utils.responses import error, success
from utils.validators import ValidationError

PUBLIC_API_PATHS = {
    "/api/health",
    "/api/register",
    "/api/login",
}
PUBLIC_API_PREFIXES = ("/api/auth/",)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    app.json.sort_keys = False

    CORS(
        app,
        resources={r"/api/*": {"origins": Config.CORS_ORIGINS}},
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
        expose_headers=["Content-Disposition"],
        max_age=86400,
    )

    if Config.DB_ENGINE == "sqlite":
        db.init_sqlite()

    app.register_blueprint(auth_bp, url_prefix="/api")
    app.register_blueprint(transactions_bp, url_prefix="/api/transactions")
    app.register_blueprint(dashboard_bp, url_prefix="/api/dashboard")
    app.register_blueprint(budgets_bp, url_prefix="/api/budgets")
    app.register_blueprint(ml_bp, url_prefix="/api")
    app.register_blueprint(insights_bp, url_prefix="/api/insights")
    app.register_blueprint(chatbot_bp, url_prefix="/api/chatbot")
    app.register_blueprint(reports_bp, url_prefix="/api/reports")

    @app.before_request
    def protect_api():
        if request.method == "OPTIONS":
            return None
        path = request.path.rstrip("/") or "/"
        if not path.startswith("/api/"):
            return None
        if path in PUBLIC_API_PATHS or any(path.startswith(prefix.rstrip("/")) for prefix in PUBLIC_API_PREFIXES):
            return None
        return authenticate_request()

    @app.get("/api/health")
    def health():
        database_ok = db.healthcheck()
        payload = {
            "status": "healthy" if database_ok else "degraded",
            "database": {"engine": Config.DB_ENGINE, "connected": database_ok},
            "classifier": {"available": model_info().get("available", False)},
            "forecaster": {"available": forecast_info().get("available", False)},
        }
        return success(payload, status=200 if database_ok else 503)

    @app.errorhandler(ValidationError)
    def handle_validation(exc):
        return error(str(exc), 422)

    @app.errorhandler(413)
    def too_large(_exc):
        return error("Request payload is too large", 413)

    @app.errorhandler(404)
    def not_found(_exc):
        if request.path.startswith("/api/"):
            return error("Endpoint not found", 404)
        return jsonify({"success": False, "message": "Resource not found"}), 404

    @app.errorhandler(405)
    def method_not_allowed(_exc):
        return error("Method not allowed for this endpoint", 405)

    @app.errorhandler(Exception)
    def handle_exception(exc):
        if isinstance(exc, HTTPException):
            return error(exc.description or "Request failed", exc.code or 500)
        logger.exception("Unhandled server error: %s", exc)
        if Config.DEBUG:
            return error(f"Internal server error: {exc}", 500)
        return error("An unexpected server error occurred", 500)

    frontend_dist = PROJECT_ROOT / "frontend" / "dist"
    if frontend_dist.exists():
        @app.get("/")
        def serve_frontend():
            return send_from_directory(frontend_dist, "index.html")

        @app.get("/<path:path>")
        def serve_static(path: str):
            candidate = frontend_dist / path
            if candidate.is_file():
                return send_from_directory(frontend_dist, path)
            return send_from_directory(frontend_dist, "index.html")

    return app


app = create_app()


if __name__ == "__main__":
    print(f"Finora API running on http://localhost:{Config.__dict__.get('PORT', 5000)}")
    print(f"Database engine: {Config.DB_ENGINE}")
    app.run(host="0.0.0.0", port=5000, debug=Config.DEBUG)
