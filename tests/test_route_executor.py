import csv
import io
import sys
import unittest
from pathlib import Path
import zipfile


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from route_executor import execute_plan, serialize_customer_export  # noqa: E402
from route_planner import plan_query  # noqa: E402
from xiaoman_client import ListResult  # noqa: E402


class FakeClient:
    def __init__(self):
        self.calls = []
        self.tenant_id = "test-tenant"
        self.scope = "company user lead opportunity invoices"

    def get_customer_detail(self, **kwargs):
        self.calls.append(("get_customer_detail", kwargs))
        return {"company_id": 101, "name": "ABC", "recent_follow_up_time": "2026-11-01 10:00:00", "customers": []}

    def list_followup_trails(self, **kwargs):
        self.calls.append(("list_followup_trails", kwargs))
        return ListResult(
            [{"trail_id": 1, "company_id": 101, "content": "redacted"}],
            1,
            1,
            True,
            "total_item_reached",
        )

    def list_customers(self, **kwargs):
        self.calls.append(("list_customers", kwargs))
        return ListResult([{"company_id": 101, "name": "ABC"}], 1, 1, True, "total_item_reached")

    def list_users(self, **kwargs):
        self.calls.append(("list_users", kwargs))
        return ListResult([{"user_id": 7, "nickname": "Seller"}], 1, 1, True, "total_item_reached")


class RouteExecutorTests(unittest.TestCase):
    def test_timeline_plan_consumes_customer_ref_and_days(self):
        client = FakeClient()
        plan = plan_query("客户 ABC 最近90天的跟进记录")

        result = execute_plan(client, plan)

        self.assertTrue(result["complete"])
        self.assertEqual(result["data"]["customer"]["company_id"], 101)
        self.assertEqual(result["data"]["trails"]["items"][0]["trail_id"], 1)
        self.assertEqual(result["data"]["metrics"]["trail_count"], 1)
        self.assertEqual(result["data"]["metrics"]["type_counts"], {"unknown": 1})
        self.assertEqual(client.calls[1][1]["company_id"], 101)
        self.assertIn("start_time", client.calls[1][1])

    def test_export_serialization_is_deterministic_csv(self):
        output = serialize_customer_export(
            [{"company_id": 1, "name": "ABC", "short_name": "A"}], "csv"
        )

        rows = list(csv.DictReader(io.StringIO(output)))
        self.assertEqual(rows, [{"company_id": "1", "name": "ABC", "short_name": "A"}])

    def test_export_serialization_supports_xlsx(self):
        output = serialize_customer_export([{"company_id": 1, "name": "ABC"}], "xlsx")

        self.assertIsInstance(output, bytes)
        with zipfile.ZipFile(io.BytesIO(output)) as archive:
            self.assertIn("xl/worksheets/sheet1.xml", archive.namelist())
            self.assertIsNone(archive.testzip())

    def test_export_plan_returns_serialized_csv_payload(self):
        result = execute_plan(FakeClient(), plan_query("把所有客户提取成 CSV"))

        self.assertTrue(result["complete"])
        self.assertEqual(result["export"]["encoding"], "utf-8")
        self.assertIn("company_id", result["export"]["content"])

    def test_missing_scope_is_returned_as_a_reportable_gap(self):
        client = FakeClient()
        client.scope = "company"

        result = execute_plan(client, plan_query("分析线索到商机的销售漏斗"))

        self.assertFalse(result["complete"])
        self.assertEqual(result["missing_scopes"], ["lead", "opportunity"])
        self.assertEqual(client.calls, [])

    def test_missing_tenant_profile_is_returned_as_a_reportable_gap(self):
        client = FakeClient()
        client.tenant_id = None

        result = execute_plan(client, plan_query("找出30天没跟进的客户"))

        self.assertFalse(result["complete"])
        self.assertEqual(result["missing_profile"], "tenant_id")
        self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main()
