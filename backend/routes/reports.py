"""Reports and export routes."""
from __future__ import annotations

from flask import Blueprint, g, request, send_file

from services.report_service import build_report, export_report
from utils.responses import error, success

reports_bp = Blueprint("reports", __name__)


@reports_bp.get("")
@reports_bp.get("/")
def reports():
    try:
        data = build_report(g.current_user["user_id"], request.args.get("month"))
        # Keep list endpoints light; the full transaction list is available separately.
        data["transactions"] = data["transactions"][:10]
        return success(data)
    except ValueError as exc:
        return error(str(exc), 422)
    except Exception as exc:  # pragma: no cover - defensive API boundary
        return error(f"Unable to build report: {exc}", 500)


@reports_bp.get("/export")
def export():
    export_format = (request.args.get("format") or "csv").lower()
    if export_format not in {"csv", "pdf"}:
        return error("Export format must be csv or pdf", 422)
    try:
        buffer, mimetype, filename = export_report(
            g.current_user["user_id"],
            request.args.get("month"),
            export_format,
        )
        return send_file(
            buffer,
            mimetype=mimetype,
            as_attachment=True,
            download_name=filename,
            max_age=0,
        )
    except ValueError as exc:
        return error(str(exc), 422)
    except RuntimeError as exc:
        return error(str(exc), 503)
    except Exception as exc:  # pragma: no cover - defensive API boundary
        return error(f"Unable to export report: {exc}", 500)
