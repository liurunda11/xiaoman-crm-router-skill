"""Pure natural-language routing for the Xiaoman CRM Skill.

This module intentionally contains no network calls.  It turns a user request
into a small, read-only execution plan that the API adapter can run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
import sys
from typing import Any


@dataclass(frozen=True)
class Operation:
    name: str
    endpoint: str
    scope: str


@dataclass
class QueryPlan:
    intent: str
    operations: list[Operation]
    parameters: dict[str, Any] = field(default_factory=dict)
    read_only: bool = True


LIST_CUSTOMERS = Operation(
    name="list_customers", endpoint="GET /v1/company/list", scope="company"
)
GET_CUSTOMER_DETAIL = Operation(
    name="get_customer_detail", endpoint="GET /v1/company/info", scope="company"
)
LIST_FOLLOWUP_TRAILS = Operation(
    name="list_followup_trails",
    endpoint="GET /v1/dynamic/trail/list",
    scope="company",
)
LIST_USERS = Operation(name="list_users", endpoint="GET /v1/user/list", scope="user")
LIST_LEADS = Operation(name="list_leads", endpoint="GET /v1/lead/list", scope="lead")
LIST_OPPORTUNITIES = Operation(
    name="list_opportunities", endpoint="GET /v1/opportunity/list", scope="opportunity"
)
LIST_ORDERS = Operation(
    name="list_orders", endpoint="GET /v1/invoices/order/list", scope="invoices"
)


def _extract_customer_ref(query: str) -> str | None:
    match = re.search(r"客户\s*([A-Za-z0-9][A-Za-z0-9_-]*)", query)
    return match.group(1) if match else None


def _extract_stale_days(query: str) -> int:
    match = re.search(r"(\d+)\s*天", query)
    return int(match.group(1)) if match else 30


def _extract_export_format(query: str) -> str:
    lowered = query.lower()
    if "excel" in lowered or "xlsx" in lowered or "表格" in query:
        return "xlsx"
    if "json" in lowered:
        return "json"
    return "csv"


def plan_query(query: str) -> QueryPlan:
    """Return the smallest safe read-only plan for a Xiaoman CRM question."""

    if any(word in query for word in ("移入公海", "删除客户", "新增客户", "编辑客户", "提交跟进")):
        return QueryPlan(intent="unsupported_write", operations=[])

    if "所有客户" in query and any(word in query.lower() for word in ("csv", "excel", "xlsx", "json", "提取", "导出")):
        return QueryPlan(
            intent="export_customers",
            operations=[LIST_CUSTOMERS, GET_CUSTOMER_DETAIL],
            parameters={"format": _extract_export_format(query), "all": 1},
        )

    if "销售漏斗" in query or ("线索" in query and "商机" in query and "分析" in query):
        operations = [LIST_LEADS, LIST_OPPORTUNITIES, LIST_FOLLOWUP_TRAILS]
        if any(word in query for word in ("订单", "成交", "回款")):
            operations.append(LIST_ORDERS)
        return QueryPlan(
            intent="pipeline_analysis",
            operations=operations,
        )

    if "客户" in query and any(word in query for word in ("跟进记录", "跟进时间线", "跟进历史")):
        customer_ref = _extract_customer_ref(query)
        if not customer_ref:
            return QueryPlan(
                intent="needs_clarification",
                operations=[],
                parameters={"missing": ["customer_ref"]},
            )
        return QueryPlan(
            intent="followup_timeline",
            operations=[GET_CUSTOMER_DETAIL, LIST_FOLLOWUP_TRAILS],
            parameters={
                "customer_ref": customer_ref,
                "days": _extract_stale_days(query),
            },
        )

    if any(word in query for word in ("没跟进", "未跟进", "未联系", "长期未")):
        return QueryPlan(
            intent="stale_followups",
            operations=[LIST_CUSTOMERS, LIST_FOLLOWUP_TRAILS],
            parameters={"stale_days": _extract_stale_days(query)},
        )

    if "客户" in query and any(word in query for word in ("画像", "联系人", "负责人", "详细", "介绍")):
        operations = [GET_CUSTOMER_DETAIL]
        if "负责人" in query:
            operations.append(LIST_USERS)
        return QueryPlan(
            intent="customer_profile",
            operations=operations,
            parameters={"customer_ref": _extract_customer_ref(query)},
        )

    if any(word in query for word in ("客户列表", "客户有哪些", "列出客户")):
        return QueryPlan(intent="customer_search", operations=[LIST_CUSTOMERS])

    return QueryPlan(intent="needs_clarification", operations=[])


def _plan_as_dict(plan: QueryPlan) -> dict[str, Any]:
    return {
        "intent": plan.intent,
        "operations": [
            {"name": operation.name, "endpoint": operation.endpoint, "scope": operation.scope}
            for operation in plan.operations
        ],
        "parameters": plan.parameters,
        "read_only": plan.read_only,
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: route_planner.py 'user question'")
    print(json.dumps(_plan_as_dict(plan_query(sys.argv[1])), ensure_ascii=False, indent=2))

