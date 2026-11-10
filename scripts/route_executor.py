"""Execute read-only query plans against the Xiaoman client."""

from __future__ import annotations

import csv
import base64
from collections import Counter
from datetime import datetime, timedelta
import io
import json
from zipfile import ZIP_DEFLATED, ZipFile
from xml.sax.saxutils import escape
from typing import Any

from route_planner import QueryPlan


def _list_dict(result: Any) -> dict[str, Any]:
    if hasattr(result, "to_dict"):
        return result.to_dict()
    if isinstance(result, list):
        return {"items": result, "total_item": len(result), "pages": 1, "complete": True, "stop_reason": "legacy_list"}
    raise TypeError("list operation must return ListResult or list")


def _ref_kwargs(value: str | None, *, company: bool = True) -> dict[str, Any]:
    if not value:
        raise ValueError("customer reference is required")
    if value.isdigit() and company:
        return {"company_id": int(value)}
    return {"serial_id": value}


def _time_window(days: int, now: datetime | None = None) -> tuple[str, str]:
    end = now or datetime.now()
    start = end - timedelta(days=days)
    return start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")


def _parse_time(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def summarize_trails(
    result: dict[str, Any], *, now: datetime | None = None, next_follow_up_time: str | None = None
) -> dict[str, Any]:
    """Compute deterministic follow-up metrics before any language-model summary."""

    items = result.get("items", [])
    type_counts = Counter(str(item.get("type", "unknown")) for item in items)
    timestamps = [
        str(next((item.get(key) for key in ("created_at", "create_time", "update_time") if item.get(key)), ""))
        for item in items
        if next((item.get(key) for key in ("created_at", "create_time", "update_time") if item.get(key)), None)
    ]
    current = now or datetime.now()
    last_time = _parse_time(max(timestamps)) if timestamps else None
    next_time = _parse_time(next_follow_up_time)
    return {
        "trail_count": len(items),
        "type_counts": dict(sorted(type_counts.items())),
        "last_followup_at": max(timestamps) if timestamps else None,
        "silence_days": max(0, (current - last_time).days) if last_time else None,
        "stage_duration_days": None,
        "overdue_next_action": bool(next_time and next_time < current),
        "unique_operators": len({str(item.get("create_user")) for item in items if item.get("create_user") is not None}),
    }


def summarize_pipeline(
    leads: dict[str, Any],
    opportunities: dict[str, Any],
    orders: dict[str, Any] | None,
    trails: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    stage_counts = Counter(
        str(item.get("stage_type_name", item.get("stage_type", "unknown")))
        for item in opportunities.get("items", [])
    )
    return {
        "lead_count": len(leads.get("items", [])),
        "opportunity_count": len(opportunities.get("items", [])),
        "order_count": len(orders.get("items", [])) if orders else 0,
        "followup_count": sum(item.get("metrics", {}).get("trail_count", 0) for item in trails.values()),
        "opportunity_stage_counts": dict(sorted(stage_counts.items())),
    }


def execute_plan(client: Any, plan: QueryPlan, *, now: datetime | None = None) -> dict[str, Any]:
    """Execute a plan and return data plus explicit completeness metadata."""

    operation_names = [operation.name for operation in plan.operations]
    if plan.intent == "unsupported_write":
        return {
            "intent": plan.intent,
            "operations": [],
            "complete": False,
            "failed_ids": [],
            "error": "read-only router does not execute write operations",
            "data": None,
        }

    if plan.intent == "needs_clarification":
        return {
            "intent": plan.intent,
            "operations": operation_names,
            "complete": False,
            "failed_ids": [],
            "missing": plan.parameters.get("missing", []),
            "data": None,
        }

    tenant_id = getattr(client, "tenant_id", None)
    if not tenant_id:
        return {
            "intent": plan.intent,
            "operations": operation_names,
            "complete": False,
            "failed_ids": [],
            "missing_profile": "tenant_id",
            "data": None,
        }
    configured_scopes = set(str(getattr(client, "scope", "")).split())
    missing_scopes = sorted({operation.scope for operation in plan.operations} - configured_scopes)
    if missing_scopes:
        return {
            "intent": plan.intent,
            "operations": operation_names,
            "complete": False,
            "failed_ids": [],
            "missing_scopes": missing_scopes,
            "data": None,
        }

    if plan.intent == "customer_search":
        result = client.list_customers()
        metadata = _list_dict(result)
        return {"intent": plan.intent, "operations": operation_names, "complete": metadata["complete"], "failed_ids": [], "data": metadata}

    if plan.intent == "customer_profile":
        detail = client.get_customer_detail(**_ref_kwargs(plan.parameters.get("customer_ref")))
        data: dict[str, Any] = {"customer": detail}
        if "list_users" in operation_names:
            data["users"] = _list_dict(client.list_users())
        return {"intent": plan.intent, "operations": operation_names, "complete": True, "failed_ids": [], "data": data}

    if plan.intent == "followup_timeline":
        detail = client.get_customer_detail(**_ref_kwargs(plan.parameters.get("customer_ref")))
        start_time, end_time = _time_window(int(plan.parameters.get("days", 30)), now)
        trails = client.list_followup_trails(
            company_id=detail["company_id"], start_time=start_time, end_time=end_time
        )
        trails_data = _list_dict(trails)
        return {
            "intent": plan.intent,
            "operations": operation_names,
            "complete": trails_data["complete"],
            "failed_ids": [],
            "data": {
                "customer": detail,
                "trails": trails_data,
                "metrics": summarize_trails(
                    trails_data,
                    now=now,
                    next_follow_up_time=detail.get("next_follow_up_time"),
                ),
                "start_time": start_time,
                "end_time": end_time,
            },
        }

    if plan.intent == "export_customers":
        summaries = client.list_customers(all=1)
        summary_data = _list_dict(summaries)
        details: list[dict[str, Any]] = []
        failed_ids: list[Any] = []
        for row in summary_data["items"]:
            company_id = row.get("company_id")
            try:
                details.append(client.get_customer_detail(company_id=company_id))
            except Exception:
                failed_ids.append(company_id)
        return {
            "intent": plan.intent,
            "operations": operation_names,
            "complete": summary_data["complete"] and not failed_ids,
            "failed_ids": failed_ids,
            "format": plan.parameters.get("format", "csv"),
            "data": {"summaries": summary_data, "details": details},
            "export": _encoded_export(details, plan.parameters.get("format", "csv")),
        }

    if plan.intent == "stale_followups":
        summaries = client.list_customers()
        summary_data = _list_dict(summaries)
        start_time, end_time = _time_window(int(plan.parameters.get("stale_days", 30)), now)
        stale: list[dict[str, Any]] = []
        failed_ids: list[Any] = []
        for row in summary_data["items"]:
            company_id = row.get("company_id")
            try:
                detail = client.get_customer_detail(company_id=company_id)
                trails = _list_dict(
                    client.list_followup_trails(company_id=company_id, start_time=start_time, end_time=end_time)
                )
                if not trails["items"]:
                    stale.append(
                        {
                            "customer": detail,
                            "trails": trails,
                            "metrics": summarize_trails(
                                trails,
                                now=now,
                                next_follow_up_time=detail.get("next_follow_up_time"),
                            ),
                        }
                    )
                if not trails["complete"]:
                    failed_ids.append(company_id)
            except Exception:
                failed_ids.append(company_id)
        return {
            "intent": plan.intent,
            "operations": operation_names,
            "complete": summary_data["complete"] and not failed_ids,
            "failed_ids": failed_ids,
            "data": {"stale": stale, "start_time": start_time, "end_time": end_time},
        }

    if plan.intent == "pipeline_analysis":
        leads = _list_dict(client.list_leads())
        opportunities = _list_dict(client.list_opportunities())
        orders = _list_dict(client.list_orders()) if "list_orders" in operation_names else None
        trail_map: dict[str, dict[str, Any]] = {}
        failed_ids: list[Any] = []
        for lead in leads["items"]:
            lead_id = lead.get("lead_id")
            if lead_id is None:
                continue
            try:
                raw_trails = _list_dict(client.list_followup_trails(lead_id=lead_id))
                trail_map[f"lead:{lead_id}"] = {
                    "items": raw_trails["items"],
                    "complete": raw_trails["complete"],
                    "metrics": summarize_trails(raw_trails, now=now),
                }
            except Exception:
                failed_ids.append(lead_id)
        for opportunity in opportunities["items"]:
            opportunity_id = opportunity.get("opportunity_id")
            if opportunity_id is None:
                continue
            try:
                raw_trails = _list_dict(client.list_followup_trails(opportunity_id=opportunity_id))
                trail_map[f"opportunity:{opportunity_id}"] = {
                    "items": raw_trails["items"],
                    "complete": raw_trails["complete"],
                    "metrics": summarize_trails(raw_trails, now=now),
                }
            except Exception:
                failed_ids.append(opportunity_id)
        complete = leads["complete"] and opportunities["complete"] and not failed_ids and all(
            trail.get("complete", False) for trail in trail_map.values()
        )
        if orders is not None:
            complete = complete and orders["complete"]
        order_map: dict[str, list[dict[str, Any]]] = {}
        if orders is not None:
            for order in orders["items"]:
                opportunity_id = order.get("opportunity_id")
                if opportunity_id is not None:
                    order_map.setdefault(str(opportunity_id), []).append(order)
        return {
            "intent": plan.intent,
            "operations": operation_names,
            "complete": complete,
            "failed_ids": failed_ids,
            "data": {
                "leads": leads,
                "opportunities": opportunities,
                "orders": orders,
                "orders_by_opportunity": order_map,
                "trails": trail_map,
                "metrics": summarize_pipeline(leads, opportunities, orders, trail_map),
            },
        }

    return {
        "intent": plan.intent,
        "operations": operation_names,
        "complete": False,
        "failed_ids": [],
        "error": "query needs clarification",
        "data": None,
    }


def _xlsx_cell(value: Any) -> str:
    if value is None:
        text = ""
    elif isinstance(value, (str, int, float, bool)):
        text = str(value)
    else:
        text = json.dumps(value, ensure_ascii=False)
    return f'<c t="inlineStr"><is><t>{escape(text)}</t></is></c>'


def _serialize_xlsx(records: list[dict[str, Any]]) -> bytes:
    keys = sorted({key for record in records for key in record})
    rows = [keys, *[[record.get(key) for key in keys] for record in records]]
    sheet_rows = []
    for row_number, row in enumerate(rows, 1):
        cells = "".join(_xlsx_cell(value) for value in row)
        sheet_rows.append(f'<row r="{row_number}">{cells}</row>')
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(sheet_rows)}</sheetData></worksheet>'
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Customers" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/></Relationships>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/></Relationships>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '</Types>'
    )
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", workbook_rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", rels)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return buffer.getvalue()


def serialize_customer_export(records: list[dict[str, Any]], format: str) -> str | bytes:
    """Serialize flat or nested customer rows as JSON or deterministic CSV."""

    if format == "json":
        return json.dumps(records, ensure_ascii=False, indent=2)
    if format == "xlsx":
        return _serialize_xlsx(records)
    if format != "csv":
        raise ValueError("export format must be csv, json, or xlsx")
    keys = sorted({key for record in records for key in record})
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=keys, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for record in records:
        row = {
            key: value if isinstance(value, (str, int, float, bool)) or value is None else json.dumps(value, ensure_ascii=False)
            for key, value in record.items()
        }
        writer.writerow(row)
    return stream.getvalue()


def _encoded_export(records: list[dict[str, Any]], format: str) -> dict[str, str]:
    payload = serialize_customer_export(records, format)
    if isinstance(payload, bytes):
        return {"encoding": "base64", "content": base64.b64encode(payload).decode("ascii")}
    return {"encoding": "utf-8", "content": payload}

