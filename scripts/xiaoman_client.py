"""Small, dependency-free, read-only client for Xiaoman Open API."""

from __future__ import annotations

from dataclasses import dataclass
import argparse
import json
import os
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class XiaomanApiError(RuntimeError):
    """An API response that cannot be safely treated as success."""

    def __init__(self, status: int, payload: Any):
        self.status = status
        self.payload = payload
        super().__init__(f"Xiaoman API request failed with status {status}: {payload}")


class XiaomanScopeError(PermissionError):
    """The configured token scope cannot access the requested module."""

    def __init__(self, required_scope: str, configured_scope: str):
        self.required_scope = required_scope
        self.configured_scope = configured_scope
        super().__init__(
            f"scope '{required_scope}' is required; configured scopes: {configured_scope or '[none]'}"
        )


@dataclass
class _Token:
    value: str
    token_type: str = "Bearer"


@dataclass
class ListResult:
    items: list[dict[str, Any]]
    total_item: int | None
    pages: int
    complete: bool
    stop_reason: str
    tenant_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": self.items,
            "total_item": self.total_item,
            "pages": self.pages,
            "complete": self.complete,
            "stop_reason": self.stop_reason,
            "tenant_id": self.tenant_id,
        }


Transport = Callable[[str, str, dict[str, str], bytes | None], tuple[int, Any]]


class XiaomanClient:
    """Read-only Xiaoman client with auth, pagination, retry, and normalization."""

    def __init__(
        self,
        base_url: str,
        client_id: str,
        client_secret: str,
        *,
        scope: str = "company",
        tenant_id: str | None = None,
        transport: Transport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_retries: int = 2,
        page_size: int = 20,
    ):
        if not tenant_id:
            raise ValueError("tenant_id is required to keep CRM enterprises isolated")
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.scope = scope
        self.tenant_id = tenant_id
        self._transport = transport or self._urllib_transport
        self._sleep = sleep
        self.max_retries = max_retries
        self.page_size = page_size
        self._token: _Token | None = None

    def authenticate(self) -> dict[str, Any]:
        body = urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": self.scope,
            }
        ).encode()
        status, payload = self._request_raw(
            "POST", "/v1/oauth2/access_token", headers={"Content-Type": "application/x-www-form-urlencoded"}, body=body
        )
        if status < 200 or status >= 300 or not isinstance(payload, dict):
            raise XiaomanApiError(status, payload)
        token = payload.get("access_token")
        if not token:
            raise XiaomanApiError(status, {"message": "missing access_token", "payload": payload})
        self._token = _Token(token, payload.get("token_type", "Bearer"))
        return payload

    def list_customers(self, *, page_size: int | None = None, **filters: Any) -> ListResult:
        self._require_scope("company")
        return self._list_pages("/v1/company/list", page_size=page_size, **filters)

    def list_users(self, *, page_size: int | None = None, **filters: Any) -> ListResult:
        self._require_scope("user")
        return self._list_pages("/v1/user/list", page_size=page_size, **filters)

    def list_leads(self, *, page_size: int | None = None, **filters: Any) -> ListResult:
        self._require_scope("lead")
        return self._list_pages("/v1/lead/list", page_size=page_size, **filters)

    def get_lead_detail(
        self, *, lead_id: int | str | None = None, serial_id: str | None = None
    ) -> dict[str, Any]:
        self._require_scope("lead")
        if lead_id is None and serial_id is None:
            raise ValueError("lead_id or serial_id is required")
        params = {key: value for key, value in {"lead_id": lead_id, "serial_id": serial_id}.items() if value is not None}
        payload = self._request_json("GET", "/v1/lead/info", params=params)
        return self._data_object(payload)

    def list_opportunities(self, *, page_size: int | None = None, **filters: Any) -> ListResult:
        self._require_scope("opportunity")
        return self._list_pages("/v1/opportunity/list", page_size=page_size, **filters)

    def list_orders(self, *, page_size: int | None = None, **filters: Any) -> ListResult:
        self._require_scope("invoices")
        return self._list_pages("/v1/invoices/order/list", page_size=page_size, **filters)

    def get_customer_detail(
        self, *, company_id: int | str | None = None, serial_id: str | None = None, format: int = 1
    ) -> dict[str, Any]:
        self._require_scope("company")
        if company_id is None and serial_id is None:
            raise ValueError("company_id or serial_id is required")
        params = {"format": format}
        if company_id is not None:
            params["company_id"] = company_id
        if serial_id is not None:
            params["serial_id"] = serial_id
        payload = self._request_json("GET", "/v1/company/info", params=params)
        return self._data_object(payload)

    def list_followup_trails(
        self,
        *,
        company_id: int | str | None = None,
        lead_id: int | str | None = None,
        opportunity_id: int | str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        page_size: int | None = None,
    ) -> ListResult:
        self._require_scope("company")
        identifiers = [company_id is not None, lead_id is not None, opportunity_id is not None]
        if sum(identifiers) != 1:
            raise ValueError("exactly one of company_id, lead_id, or opportunity_id is required")
        filters = {
            key: value
            for key, value in {
                "company_id": company_id,
                "lead_id": lead_id,
                "opportunity_id": opportunity_id,
                "start_time": start_time,
                "end_time": end_time,
            }.items()
            if value is not None
        }
        return self._list_pages("/v1/dynamic/trail/list", page_size=page_size, **filters)

    def _list_pages(self, path: str, *, page_size: int | None = None, **filters: Any) -> ListResult:
        count = self.page_size if page_size is None else page_size
        if count <= 0:
            raise ValueError("page_size must be positive")
        rows: list[dict[str, Any]] = []
        start_index = 1
        pages = 0
        total_item: int | None = None
        while True:
            params = {key: value for key, value in filters.items() if value is not None}
            params.update({"count": count, "start_index": start_index})
            payload = self._request_json("GET", path, params=params)
            data = payload.get("data") or {}
            if not isinstance(data, dict):
                raise XiaomanApiError(200, {"message": "data is not an object", "payload": payload})
            if "list" not in data:
                raise XiaomanApiError(200, {"message": "data.list is missing", "payload": payload})
            page = data.get("list") or []
            if not isinstance(page, list):
                raise XiaomanApiError(200, {"message": "data.list is not a list", "payload": payload})
            if not all(isinstance(item, dict) for item in page):
                raise XiaomanApiError(200, {"message": "data.list contains a non-object item", "payload": payload})
            rows.extend(page)
            pages += 1
            if isinstance(data.get("totalItem"), int):
                total_item = data["totalItem"]
            if total_item is not None and len(rows) >= total_item:
                return ListResult(rows, total_item, pages, True, "total_item_reached", self.tenant_id)
            if not page:
                return ListResult(rows, total_item, pages, total_item == len(rows), "empty_page", self.tenant_id)
            if len(page) < count:
                return ListResult(
                    rows,
                    total_item,
                    pages,
                    total_item is not None and len(rows) >= total_item,
                    "short_page",
                    self.tenant_id,
                )
            start_index += 1

    def _require_scope(self, required_scope: str) -> None:
        configured = set(self.scope.split())
        if required_scope not in configured:
            raise XiaomanScopeError(required_scope, self.scope)

    def _request_json(self, method: str, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._token is None:
            self.authenticate()
        query = urlencode(params or {}, doseq=True)
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{query}"
        headers = {"Authorization": f"{self._token.token_type} {self._token.value}"}
        status, payload = self._request_raw(method, url, headers=headers, body=None)
        if status == 401:
            self._token = None
            self.authenticate()
            headers = {"Authorization": f"{self._token.token_type} {self._token.value}"}
            status, payload = self._request_raw(method, url, headers=headers, body=None)
        if status < 200 or status >= 300 or not isinstance(payload, dict):
            raise XiaomanApiError(status, payload)
        if payload.get("_invalid_json"):
            raise XiaomanApiError(status, payload)
        if payload.get("code") not in (None, 200):
            raise XiaomanApiError(status, payload)
        return payload

    def _request_raw(
        self, method: str, url_or_path: str, *, headers: dict[str, str], body: bytes | None
    ) -> tuple[int, Any]:
        url = url_or_path if url_or_path.startswith("http") else f"{self.base_url}{url_or_path}"
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                status, payload = self._transport(method, url, headers, body)
            except (HTTPError, URLError, TimeoutError) as error:
                last_error = error
                if attempt >= self.max_retries:
                    raise XiaomanApiError(599, {"message": str(error)}) from error
                self._sleep(2**attempt)
                continue
            if status in (429,) or 500 <= status <= 599:
                if attempt >= self.max_retries:
                    return status, payload
                self._sleep(2**attempt)
                continue
            return status, payload
        raise XiaomanApiError(599, {"message": str(last_error)})

    @staticmethod
    def _data_object(payload: dict[str, Any]) -> dict[str, Any]:
        data = payload.get("data")
        if not isinstance(data, dict):
            raise XiaomanApiError(200, {"message": "data is not an object", "payload": payload})
        return data

    @staticmethod
    def _urllib_transport(method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, Any]:
        request = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=60) as response:
                raw = response.read().decode("utf-8")
                try:
                    payload: Any = json.loads(raw) if raw else {}
                except json.JSONDecodeError:
                    payload = {"_invalid_json": True, "message": "invalid JSON response"}
                return response.status, payload
        except HTTPError as error:
            raw = error.read().decode("utf-8", errors="replace")
            try:
                payload: Any = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                payload = {"message": raw}
            return error.code, payload


def _main() -> None:
    parser = argparse.ArgumentParser(description="Read-only Xiaoman API helper")
    parser.add_argument(
        "command",
        choices=(
            "list-customers",
            "customer-detail",
            "list-followups",
            "list-leads",
            "lead-detail",
            "list-opportunities",
            "list-orders",
            "list-users",
        ),
    )
    parser.add_argument("--company-id")
    parser.add_argument("--lead-id")
    parser.add_argument("--opportunity-id")
    parser.add_argument("--serial-id")
    parser.add_argument("--start-time")
    parser.add_argument("--end-time")
    parser.add_argument("--page-size", type=int, default=20)
    args = parser.parse_args()

    required = ("XIAOMAN_BASE_URL", "XIAOMAN_CLIENT_ID", "XIAOMAN_CLIENT_SECRET")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise SystemExit(f"missing environment variables: {', '.join(missing)}")
    client = XiaomanClient(
        os.environ["XIAOMAN_BASE_URL"],
        os.environ["XIAOMAN_CLIENT_ID"],
        os.environ["XIAOMAN_CLIENT_SECRET"],
        scope=os.environ.get("XIAOMAN_SCOPE", "company"),
        tenant_id=os.environ.get("XIAOMAN_TENANT_ID"),
        page_size=args.page_size,
    )
    if args.command == "list-customers":
        result = client.list_customers(page_size=args.page_size)
    elif args.command == "customer-detail":
        result = client.get_customer_detail(company_id=args.company_id, serial_id=args.serial_id)
    elif args.command == "list-followups":
        result = client.list_followup_trails(
            company_id=args.company_id,
            lead_id=args.lead_id,
            opportunity_id=args.opportunity_id,
            start_time=args.start_time,
            end_time=args.end_time,
            page_size=args.page_size,
        )
    elif args.command == "list-leads":
        result = client.list_leads(page_size=args.page_size)
    elif args.command == "lead-detail":
        result = client.get_lead_detail(lead_id=args.lead_id, serial_id=args.serial_id)
    elif args.command == "list-opportunities":
        result = client.list_opportunities(page_size=args.page_size)
    elif args.command == "list-orders":
        result = client.list_orders(page_size=args.page_size)
    else:
        result = client.list_users(page_size=args.page_size)
    if isinstance(result, ListResult):
        result = result.to_dict()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _main()

