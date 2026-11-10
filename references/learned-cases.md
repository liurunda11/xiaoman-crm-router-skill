# Validated Routing Cases

Only add cases that passed the router regression suite. Keep examples脱敏 and short.

## Seed cases

- “找出30天没跟进的客户” → `stale_followups` → `company/list` + `dynamic/trail/list`.
- “看一下客户 ABC 的联系人和负责人” → `customer_profile` → `company/info` + `user/list`.
- “把所有客户提取成 CSV” → `export_customers` → `company/list` + `company/info`.
