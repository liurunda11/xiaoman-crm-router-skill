---
name: xiaoman-crm-router
description: "Route natural-language questions about Xiaoman/OKKI CRM to the minimum read-only API calls, combine customer and follow-up data, and improve routing from validated feedback."
---

# Xiaoman CRM Router

Use this skill when a user asks about 小满、Xiaoman、OKKI CRM customers, contacts, leads, follow-ups, opportunities, owners, exports, or sales-process analysis.

## Route the request

1. Read [references/api-catalog.md](references/api-catalog.md) before selecting an endpoint.
2. Extract the business object, action, filters, time range, tenant profile, and requested output.
3. Run the pure planner when useful:

   ```bash
   python3 scripts/route_planner.py "USER QUESTION"
   ```

4. Execute the plan through `scripts/route_executor.py`/`execute_plan`; it consumes IDs and time windows, attaches completeness metadata, and records failed IDs. Use `serialize_customer_export` for CSV/JSON output.
5. Choose the smallest read-only plan:
   - customer list/filter: `GET /v1/company/list`
   - customer profile/contact: `GET /v1/company/info`
   - follow-up timeline: `GET /v1/dynamic/trail/list`
   - lead lifecycle: `GET /v1/lead/list` and `GET /v1/lead/info`
   - opportunity lifecycle: `GET /v1/opportunity/list`
   - sales orders and成交金额: `GET /v1/invoices/order/list`
   - owner names: `GET /v1/user/list`
6. If the request needs all customers, paginate until `totalItem`; do not call a single page complete.
7. Join records only on documented IDs (`company_id`, `customer_id`, `lead_id`, `opportunity_id`, `user_id`).
8. If scope, permission, tenant, or an identifier is missing, report the exact gap and ask for it. Do not guess.

The route step is complete only when every selected operation has a documented endpoint, required IDs are present, and the plan declares any missing scope or profile before network work. The execution step is complete only when every list result reports `complete=true` and `failed_ids` is empty, or the answer explicitly reports the partial state.

## Execute safely

Use `scripts/xiaoman_client.py` as the only HTTP adapter. Load credentials from environment variables, never from the prompt or repository:

```text
XIAOMAN_BASE_URL
XIAOMAN_CLIENT_ID
XIAOMAN_CLIENT_SECRET
XIAOMAN_SCOPE=company
XIAOMAN_TENANT_ID
```

The adapter handles OAuth client credentials, pagination, bounded retries, 401 refresh/re-authentication, and response validation. Keep the default route read-only. Treat POST/PUT/DELETE operations as unsupported unless the user explicitly requests a separate write workflow and that workflow has been reviewed.

Every answer must state the queried range, filters, operations used, result completeness, and failed IDs. For analysis, calculate deterministic metrics first (last follow-up, silence days, count by type, stage duration, overdue next action), then add an AI summary only from the fields needed for the question.

## Reflect and improve

After each run, create a redacted trace and candidate feedback with `scripts/reflect_router.py`. Store traces and the review ledger outside the skill directory, preferably under `~/.codex/xiaoman-crm/`. Never store tokens, secrets, contact details, or full note content. Treat user corrections, API errors, empty results, and partial failures as evidence; treat silence as no evidence.

Candidates go to the review ledger and must pass `evals/router_cases.jsonl` plus existing cases before being promoted to [references/learned-cases.md](references/learned-cases.md). Use `promote_case(..., eval_path=...)`; it runs the regression suite before writing the learned-case ledger. Run the regression set with:

```bash
python3 scripts/run_router_eval.py evals/router_cases.jsonl
```

Keep core routing rules versioned and reversible; a single request must not rewrite them.

The reflection step is complete only when the trace is redacted, the candidate has an evidence category, and any promoted case has been evaluated with the candidate query included in the regression run.

If a question is unrelated to Xiaoman/OKKI CRM, do not activate this workflow.
