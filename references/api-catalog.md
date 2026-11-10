# Xiaoman API Catalog

Use this reference when the request is about Xiaoman/OKKI CRM. The workspace may contain a longer official research note, but this installed Skill must remain self-contained; re-check the official pages before adding an endpoint.

## Authentication

- Token: `POST /v1/oauth2/access_token` with `client_credentials`, `client_id`, `client_secret`, and space-separated `scope`.
- Customer scope: `company`.
- Optional scopes: `lead`, `opportunity`, `invoices`, `user`, `webhook`.
- Token lifetime is documented as about eight hours. Re-authenticate when it expires.

## Core read routes

| Need | Endpoint | Required identifiers |
| --- | --- | --- |
| Customer list/filter | `GET /v1/company/list` | `count`, `start_index`; optional `all`, `removed`, time filters |
| Customer profile/contact | `GET /v1/company/info` | `company_id` or `serial_id` |
| Customer field dictionary | `GET /v1/company/fields` | none |
| Follow-up timeline | `GET /v1/dynamic/trail/list` | one of `company_id`, `lead_id`, `opportunity_id`; optional time range |
| Lead list | `GET /v1/lead/list` | `count`, `start_index`; optional date/status filters |
| Lead detail | `GET /v1/lead/info` | `lead_id` or `serial_id` |
| Opportunity list | `GET /v1/opportunity/list` | `count`, `start_index`; optional date and stage filters |
| Sales order list | `GET /v1/invoices/order/list` | `count`, `start_index`; optional date/status filters |
| User list | `GET /v1/user/list` | pagination parameters |

## Composition rules

- Customer profile with contacts: list or resolve the customer ID, then call `company/info`.
- Single-customer follow-up: resolve the customer, then call `dynamic/trail/list` with `company_id` and a time window.
- Stale follow-up report: page through `company/list`, fetch a bounded trail window, deduplicate by trail ID, and compute silence days.
- Full customer export: page through `company/list(all=1)`, fetch details, preserve raw IDs, and report partial failures.
- Pipeline analysis: combine `lead` and `opportunity` records, attach follow-up trails by their documented IDs, and add sales orders only when the question asks about成交/订单/回款 and the `invoices` scope is available.

## Known limits

- Public docs do not state a maximum page size or tenant QPS limit.
- The public menu does not expose a separate customer export or audit-log endpoint.
- Follow-up responses show `content`, `file_info`, and `comment_count`; comment body availability needs tenant confirmation.
- Keep each CRM enterprise in a separate profile; never mix tenant data.
