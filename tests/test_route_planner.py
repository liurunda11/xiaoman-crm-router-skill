import sys
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from route_planner import plan_query  # noqa: E402


class RoutePlannerTests(unittest.TestCase):
    def test_stale_follow_up_query_uses_customer_and_trail_operations(self):
        plan = plan_query("找出30天没跟进的客户")

        self.assertEqual(plan.intent, "stale_followups")
        self.assertEqual(
            [operation.name for operation in plan.operations],
            ["list_customers", "list_followup_trails"],
        )
        self.assertEqual(plan.parameters["stale_days"], 30)
        self.assertTrue(plan.read_only)

    def test_customer_profile_query_adds_detail_only(self):
        plan = plan_query("看一下客户 ABC 的联系人和负责人")

        self.assertEqual(plan.intent, "customer_profile")
        self.assertEqual(
            [operation.name for operation in plan.operations],
            ["get_customer_detail", "list_users"],
        )
        self.assertEqual(plan.parameters["customer_ref"], "ABC")

    def test_export_all_customers_requires_explicit_full_export(self):
        plan = plan_query("把所有客户提取成 CSV")

        self.assertEqual(plan.intent, "export_customers")
        self.assertEqual(
            [operation.name for operation in plan.operations],
            ["list_customers", "get_customer_detail"],
        )
        self.assertEqual(plan.parameters["format"], "csv")

    def test_write_request_is_rejected_by_read_only_router(self):
        plan = plan_query("把客户 ABC 移入公海")

        self.assertEqual(plan.intent, "unsupported_write")
        self.assertEqual(plan.operations, [])
        self.assertTrue(plan.read_only)

    def test_single_customer_timeline_resolves_detail_before_trails(self):
        plan = plan_query("客户 ABC 最近90天的跟进记录")

        self.assertEqual(plan.intent, "followup_timeline")
        self.assertEqual(
            [operation.name for operation in plan.operations],
            ["get_customer_detail", "list_followup_trails"],
        )
        self.assertEqual(plan.parameters["customer_ref"], "ABC")
        self.assertEqual(plan.parameters["days"], 90)

    def test_timeline_without_customer_reference_needs_clarification(self):
        plan = plan_query("最近30天的客户跟进记录")

        self.assertEqual(plan.intent, "needs_clarification")
        self.assertEqual(plan.operations, [])
        self.assertEqual(plan.parameters["missing"], ["customer_ref"])

    def test_pipeline_question_composes_leads_opportunities_and_trails(self):
        plan = plan_query("分析线索到商机的销售漏斗")

        self.assertEqual(plan.intent, "pipeline_analysis")
        self.assertEqual(
            [operation.name for operation in plan.operations],
            ["list_leads", "list_opportunities", "list_followup_trails"],
        )

    def test_pipeline_order_question_adds_invoices_scope_operation(self):
        plan = plan_query("分析线索、商机和订单成交情况")

        self.assertEqual(
            [operation.name for operation in plan.operations],
            ["list_leads", "list_opportunities", "list_followup_trails", "list_orders"],
        )


if __name__ == "__main__":
    unittest.main()
