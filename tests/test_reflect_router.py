import sys
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from reflect_router import build_candidate, promote_case, redact_trace  # noqa: E402


class ReflectRouterTests(unittest.TestCase):
    def test_redacts_secrets_and_contact_data_but_keeps_route_evidence(self):
        trace = {
            "intent": "customer_profile",
            "operations": ["get_customer_detail"],
            "client_secret": "secret-value",
            "access_token": "token-value",
            "customer": {"email": "person@example.com", "tel": "123"},
            "row_count": 1,
        }

        redacted = redact_trace(trace)

        self.assertEqual(redacted["intent"], "customer_profile")
        self.assertEqual(redacted["row_count"], 1)
        self.assertEqual(redacted["client_secret"], "[REDACTED]")
        self.assertEqual(redacted["access_token"], "[REDACTED]")
        self.assertEqual(redacted["customer"]["email"], "[REDACTED]")
        self.assertEqual(redact_trace({"values": ("a", "b")})["values"], ["a", "b"])

    def test_user_correction_becomes_candidate_route_case(self):
        trace = {
            "intent": "customer_search",
            "operations": ["list_customers"],
            "parameters": {"name": "ABC"},
            "status": "ok",
        }

        candidate = build_candidate(trace, "我需要的是客户详情和联系人，不是客户列表")

        self.assertEqual(candidate["category"], "intent_or_operation")
        self.assertIn("customer_search", candidate["evidence"])
        self.assertEqual(candidate["confidence"], "high")

    def test_promotion_requires_a_passing_regression_result(self):
        candidate = build_candidate(
            {
                "query": "列出客户列表",
                "intent": "customer_search",
                "operations": ["list_customers"],
                "expected_intent": "customer_search",
                "expected_operations": ["list_customers"],
            },
            "需要客户详情",
        )
        destination = Path(self.id().replace(".", "_") + ".md")
        eval_path = Path(self.id().replace(".", "_") + ".jsonl")
        try:
            eval_path.write_text(
                '{"query":"列出客户列表","intent":"customer_search","operations":["list_customers"]}\n',
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                promote_case(destination, candidate, eval_path=Path("does-not-exist.jsonl"))
            promote_case(destination, candidate, eval_path=eval_path)
            self.assertIn(candidate["case_id"], destination.read_text(encoding="utf-8"))
        finally:
            destination.unlink(missing_ok=True)
            eval_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
