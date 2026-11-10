import sys
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from xiaoman_client import XiaomanApiError, XiaomanClient, XiaomanScopeError  # noqa: E402


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append(
            {"method": method, "url": url, "headers": headers, "body": body}
        )
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def json_response(status, payload):
    return status, payload


class XiaomanClientTests(unittest.TestCase):
    def test_tenant_profile_is_required(self):
        with self.assertRaises(ValueError):
            XiaomanClient("https://api.example.test", "client", "secret")

    def test_authenticates_once_and_paginates_until_total_item(self):
        transport = FakeTransport(
            [
                json_response(200, {"access_token": "token-1", "expires_in": 28800}),
                json_response(
                    200,
                    {"code": 200, "data": {"list": [{"company_id": 1}], "totalItem": 2}},
                ),
                json_response(
                    200,
                    {"code": 200, "data": {"list": [{"company_id": 2}], "totalItem": 2}},
                ),
            ]
        )
        client = XiaomanClient(
            "https://api.example.test", "client", "secret", tenant_id="test", transport=transport
        )

        customers = client.list_customers(page_size=1)

        self.assertEqual([row["company_id"] for row in customers.items], [1, 2])
        self.assertEqual(customers.total_item, 2)
        self.assertTrue(customers.complete)
        self.assertEqual(len(transport.calls), 3)
        self.assertEqual(transport.calls[0]["method"], "POST")
        self.assertIn("/v1/oauth2/access_token", transport.calls[0]["url"])
        self.assertEqual(transport.calls[1]["headers"]["Authorization"], "Bearer token-1")

    def test_retries_server_error_before_returning_page(self):
        transport = FakeTransport(
            [
                json_response(200, {"access_token": "token-1", "expires_in": 28800}),
                json_response(500, {"message": "temporary"}),
                json_response(
                    200,
                    {"code": 200, "data": {"list": [{"company_id": 1}], "totalItem": 1}},
                ),
            ]
        )
        client = XiaomanClient(
            "https://api.example.test",
            "client",
            "secret",
            tenant_id="test",
            transport=transport,
            sleep=lambda _: None,
        )

        self.assertEqual(client.list_customers().items, [{"company_id": 1}])
        self.assertEqual(len(transport.calls), 3)

    def test_followup_query_requires_a_related_object_id(self):
        client = XiaomanClient("https://api.example.test", "client", "secret", tenant_id="test")

        with self.assertRaises(ValueError):
            client.list_followup_trails()
        with self.assertRaises(ValueError):
            client.list_followup_trails(company_id=1, opportunity_id=2)

    def test_invalid_data_shape_is_reported_as_api_error(self):
        transport = FakeTransport(
            [
                json_response(200, {"access_token": "token-1"}),
                json_response(200, {"code": 200, "data": "not-an-object"}),
            ]
        )
        client = XiaomanClient(
            "https://api.example.test", "client", "secret", tenant_id="test", transport=transport
        )

        with self.assertRaises(XiaomanApiError):
            client.list_customers()

    def test_invalid_json_marker_is_reported_as_api_error(self):
        transport = FakeTransport(
            [
                json_response(200, {"access_token": "token-1"}),
                json_response(200, {"_invalid_json": True}),
            ]
        )
        client = XiaomanClient(
            "https://api.example.test", "client", "secret", tenant_id="test", transport=transport
        )

        with self.assertRaises(XiaomanApiError):
            client.list_customers()

    def test_zero_page_size_is_rejected_instead_of_using_default(self):
        client = XiaomanClient("https://api.example.test", "client", "secret", tenant_id="test")

        with self.assertRaises(ValueError):
            client.list_customers(page_size=0)

    def test_short_page_before_total_is_marked_incomplete(self):
        transport = FakeTransport(
            [
                json_response(200, {"access_token": "token-1"}),
                json_response(
                    200,
                    {"code": 200, "data": {"list": [{"company_id": 1}], "totalItem": 5}},
                ),
            ]
        )
        client = XiaomanClient(
            "https://api.example.test", "client", "secret", tenant_id="test", transport=transport
        )

        result = client.list_customers(page_size=20)

        self.assertFalse(result.complete)
        self.assertEqual(result.stop_reason, "short_page")

    def test_operation_scope_is_checked_before_network_call(self):
        transport = FakeTransport([])
        client = XiaomanClient(
            "https://api.example.test", "client", "secret", tenant_id="test", transport=transport, scope="company"
        )

        with self.assertRaises(XiaomanScopeError):
            client.list_users()
        self.assertEqual(transport.calls, [])


if __name__ == "__main__":
    unittest.main()
