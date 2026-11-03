"""Reports and CSV/PDF export service."""
from __future__ import annotations

import csv
import io
from datetime import date

from database import db
from models.serializers import serialize_transaction
from services.budget_service import get_budgets
from services.forecast_service import ForecastUnavailableError, user_forecast
from utils.dates import add_months, month_bounds, month_label, parse_month, today
from utils.formatters import format_inr

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
except ImportError:  # pragma: no cover
    colors = None


def _monthly_rows(user_id: int, end_year: int, end_month: int, count: int = 6) -> list[dict]:
    start_year, start_month = add_months(end_year, end_month, -(count - 1))
    start = date(start_year, start_month, 1)
    end = month_bounds(end_year, end_month)[1]
    rows = db.fetch_all(
        """
        SELECT date, type, amount FROM transactions
        WHERE user_id = %s AND date BETWEEN %s AND %s
        """,
        (user_id, start.isoformat(), end.isoformat()),
    )
    buckets = {}
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    for index in range(count):
        year, month = add_months(start_year, start_month, index)
        key = month_label(year, month)
        buckets[key] = {
            "month": key,
            "label": f"{month_names[month - 1]} {year}",
            "income": 0.0,
            "expenses": 0.0,
            "savings": 0.0,
        }
    for row in rows:
        key = str(row["date"])[:7]
        if key not in buckets:
            continue
        if row["type"] == "Income":
            buckets[key]["income"] += float(row["amount"] or 0)
        else:
            buckets[key]["expenses"] += float(row["amount"] or 0)
    for bucket in buckets.values():
        bucket["income"] = round(bucket["income"], 2)
        bucket["expenses"] = round(bucket["expenses"], 2)
        bucket["savings"] = round(bucket["income"] - bucket["expenses"], 2)
    return list(buckets.values())


def _month_summary(user_id: int, start: date, end: date) -> dict:
    rows = db.fetch_all(
        """
        SELECT type, COALESCE(SUM(amount), 0) AS total, COUNT(*) AS count
        FROM transactions
        WHERE user_id = %s AND date BETWEEN %s AND %s GROUP BY type
        """,
        (user_id, start.isoformat(), end.isoformat()),
    )
    result = {"income": 0.0, "expenses": 0.0, "count": 0}
    for row in rows:
        result["count"] += int(row["count"] or 0)
        if row["type"] == "Income":
            result["income"] = round(float(row["total"] or 0), 2)
        else:
            result["expenses"] = round(float(row["total"] or 0), 2)
    result["savings"] = round(result["income"] - result["expenses"], 2)
    result["savings_rate"] = (
        round((result["savings"] / result["income"]) * 100, 1) if result["income"] > 0 else 0
    )
    return result


def build_report(user_id: int, month: str | None = None) -> dict:
    year, month_number = parse_month(month)
    month_value = f"{year:04d}-{month_number:02d}"
    start, end = month_bounds(year, month_number)
    summary = _month_summary(user_id, start, end)

    prev_year, prev_month = add_months(year, month_number, -1)
    prev_start, prev_end = month_bounds(prev_year, prev_month)
    previous = _month_summary(user_id, prev_start, prev_end)

    category_rows = db.fetch_all(
        """
        SELECT category, COALESCE(SUM(amount), 0) AS total, COUNT(*) AS count
        FROM transactions
        WHERE user_id = %s AND type = 'Expense' AND date BETWEEN %s AND %s
        GROUP BY category ORDER BY total DESC
        """,
        (user_id, start.isoformat(), end.isoformat()),
    )
    total_expense = sum(float(row["total"] or 0) for row in category_rows)
    categories = [
        {
            "category": row["category"],
            "amount": round(float(row["total"] or 0), 2),
            "count": int(row["count"] or 0),
            "percentage": round((float(row["total"] or 0) / total_expense) * 100, 1) if total_expense else 0,
        }
        for row in category_rows
    ]

    transaction_rows = db.fetch_all(
        """
        SELECT * FROM transactions
        WHERE user_id = %s AND date BETWEEN %s AND %s
        ORDER BY date DESC, transaction_id DESC
        """,
        (user_id, start.isoformat(), end.isoformat()),
    )
    transactions = [serialize_transaction(row) for row in transaction_rows]

    budget_data = get_budgets(user_id, month_value)
    try:
        forecast = user_forecast(user_id)
    except ForecastUnavailableError:
        forecast = {"insufficient_data": True, "message": "Forecast model is not available."}

    return {
        "month": month_value,
        "month_label": date(year, month_number, 1).strftime("%B %Y"),
        "summary": summary,
        "previous": previous,
        "comparisons": {
            "income_change": _change(summary["income"], previous["income"]),
            "expense_change": _change(summary["expenses"], previous["expenses"]),
            "savings_change": _change(summary["savings"], previous["savings"]),
        },
        "categories": categories,
        "budgets": budget_data,
        "monthly_series": _monthly_rows(user_id, year, month_number, count=6),
        "transactions": transactions,
        "transaction_count": len(transactions),
        "forecast": forecast,
        "generated_at": date.today().isoformat(),
    }


def _change(current: float, previous: float) -> float:
    if previous == 0:
        return 0 if current == 0 else 100.0
    return round(((current - previous) / abs(previous)) * 100, 1)


def _csv_report(report: dict) -> io.BytesIO:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    summary = report["summary"]
    writer.writerow(["Finora - Financial Report"])
    writer.writerow(["Month", report["month_label"]])
    writer.writerow(["Generated", report["generated_at"]])
    writer.writerow([])
    writer.writerow(["Summary"])
    writer.writerow(["Metric", "Amount (INR)"])
    writer.writerow(["Total Income", f"{summary['income']:.2f}"])
    writer.writerow(["Total Expenses", f"{summary['expenses']:.2f}"])
    writer.writerow(["Savings", f"{summary['savings']:.2f}"])
    writer.writerow(["Savings Rate (%)", summary["savings_rate"]])
    writer.writerow(["Transactions", summary["count"]])
    writer.writerow([])
    writer.writerow(["Category Breakdown"])
    writer.writerow(["Category", "Amount (INR)", "Transactions", "Share (%)"])
    for item in report["categories"]:
        writer.writerow([item["category"], f"{item['amount']:.2f}", item["count"], item["percentage"]])
    writer.writerow([])
    writer.writerow(["Budget Performance"])
    writer.writerow(["Category", "Budget (INR)", "Actual (INR)", "Remaining (INR)", "Utilization (%)", "Status"])
    for item in report["budgets"]["budgets"]:
        writer.writerow(
            [
                item["category"],
                f"{item['limit_amount']:.2f}",
                f"{item['actual_expense']:.2f}",
                f"{item['remaining']:.2f}",
                item["utilization"],
                item["status"],
            ]
        )
    writer.writerow([])
    writer.writerow(["Transactions"])
    writer.writerow(["ID", "Date", "Description", "Type", "Category", "Merchant", "Amount (INR)"])
    for item in report["transactions"]:
        writer.writerow(
            [
                item["transaction_id"],
                item["date"],
                item["description"],
                item["transaction_type"],
                item["category"],
                item["merchant"],
                f"{item['amount']:.2f}",
            ]
        )
    writer.writerow([])
    forecast = report.get("forecast", {})
    writer.writerow(["Next Month Forecast (Estimate)"])
    if forecast.get("insufficient_data"):
        writer.writerow([forecast.get("message", "Insufficient historical data")])
    else:
        writer.writerow(["Predicted Month", forecast.get("predicted_month_label")])
        writer.writerow(["Estimated Total (INR)", f"{forecast.get('predicted_total', 0):.2f}"])
        writer.writerow(["Method", forecast.get("method")])

    data = buffer.getvalue().encode("utf-8-sig")
    return io.BytesIO(data)


def _pdf_report(report: dict) -> io.BytesIO:
    if colors is None:
        raise RuntimeError("PDF export requires reportlab. Install dependencies from requirements.txt")
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Finora Report - {report['month_label']}",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        textColor=colors.HexColor("#0B1F3A"),
        fontSize=21,
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        textColor=colors.HexColor("#64748B"),
        fontSize=9,
        spaceAfter=14,
    )
    heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        textColor=colors.HexColor("#0F4C81"),
        fontSize=12,
        spaceBefore=12,
        spaceAfter=7,
    )
    small_style = ParagraphStyle(
        "Small",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.HexColor("#475569"),
        leading=11,
    )

    story = [
        Paragraph("Finora", title_style),
        Paragraph(f"Financial report · {report['month_label']} · Generated {report['generated_at']}", subtitle_style),
    ]
    summary = report["summary"]
    summary_data = [
        ["Metric", "Value"],
        ["Total income", format_inr(summary["income"], symbol=False)],
        ["Total expenses", format_inr(summary["expenses"], symbol=False)],
        ["Savings", format_inr(summary["savings"], symbol=False)],
        ["Savings rate", f"{summary['savings_rate']}%"],
        ["Transactions", str(summary["count"])],
    ]
    summary_table = Table(summary_data, colWidths=[82 * mm, 82 * mm])
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F4C81")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F5F9")]),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend([Paragraph("Monthly summary", heading_style), summary_table])

    story.append(Paragraph("Category-wise expenses", heading_style))
    category_data = [["Category", "Amount (INR)", "Transactions", "Share"]]
    for item in report["categories"]:
        category_data.append(
            [item["category"], format_inr(item["amount"], symbol=False), str(item["count"]), f"{item['percentage']}%"]
        )
    if len(category_data) == 1:
        category_data.append(["No expenses recorded", "-", "-", "-"])
    category_table = Table(category_data, colWidths=[55 * mm, 45 * mm, 35 * mm, 29 * mm])
    category_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B1F3A")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                ("ALIGN", (1, 1), (3, -1), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(category_table)

    story.append(Paragraph("Budget performance", heading_style))
    budget_data = [["Category", "Budget", "Actual", "Remaining", "Used", "Status"]]
    for item in report["budgets"]["budgets"]:
        budget_data.append(
            [
                item["category"],
                format_inr(item["limit_amount"], symbol=False),
                format_inr(item["actual_expense"], symbol=False),
                format_inr(item["remaining"], symbol=False),
                f"{item['utilization']}%",
                item["status"].title(),
            ]
        )
    if len(budget_data) == 1:
        budget_data.append(["No budgets set", "-", "-", "-", "-", "-"])
    budget_table = Table(budget_data, colWidths=[32 * mm, 29 * mm, 29 * mm, 29 * mm, 20 * mm, 25 * mm])
    budget_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F766E")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F0FDFA")]),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                ("ALIGN", (1, 1), (4, -1), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(budget_table)

    story.append(Paragraph("Next month estimate", heading_style))
    forecast = report.get("forecast", {})
    if forecast.get("insufficient_data"):
        story.append(Paragraph(forecast.get("message", "Insufficient historical data."), small_style))
    else:
        story.append(
            Paragraph(
                f"Estimated total for {forecast.get('predicted_month_label')}: "
                f"{format_inr(forecast.get('predicted_total', 0), symbol=False)}. "
                f"{forecast.get('method', '')}. This is an estimate, not a guarantee.",
                small_style,
            )
        )

    story.append(Paragraph("Transactions", heading_style))
    tx_data = [["Date", "Description", "Category", "Type", "Amount (INR)"]]
    for item in report["transactions"][:80]:
        description = item["description"][:44] + ("..." if len(item["description"]) > 44 else "")
        tx_data.append(
            [
                item["date"],
                description,
                item["category"],
                item["transaction_type"],
                format_inr(item["amount"], symbol=False),
            ]
        )
    if len(tx_data) == 1:
        tx_data.append(["-", "No transactions", "-", "-", "-"])
    tx_table = Table(tx_data, colWidths=[23 * mm, 70 * mm, 27 * mm, 21 * mm, 27 * mm], repeatRows=1)
    tx_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#334155")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7.4),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
                ("ALIGN", (4, 1), (4, -1), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(tx_table)
    story.append(Spacer(1, 8))
    story.append(
        Paragraph(
            "This report is generated from the transactions recorded in Finora. "
            "Forecasts are statistical estimates and should not be treated as financial advice.",
            small_style,
        )
    )

    doc.build(story)
    buffer.seek(0)
    return buffer


def export_report(user_id: int, month: str | None, export_format: str) -> tuple[io.BytesIO, str, str]:
    report = build_report(user_id, month)
    if export_format == "pdf":
        return (
            _pdf_report(report),
            "application/pdf",
            f"finance_report_{report['month']}.pdf",
        )
    return (
        _csv_report(report),
        "text/csv",
        f"finance_report_{report['month']}.csv",
    )
