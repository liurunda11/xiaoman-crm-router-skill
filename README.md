# Xiaoman CRM Router Skill

这是一个给 Codex 使用的小满（Xiaoman/OKKI CRM）Skill。它把自然语言问题转换成最小的只读 API 调用组合，处理分页、Token、scope、租户 profile、结果完整性、导出和跟进分析，并从经过验证的反馈中积累路由案例。

仓库不包含任何 `client_secret`、Token、客户数据或运行日志。

## 安装到 Codex

在目标电脑上：

```bash
git clone https://github.com/liurunda11/xiaoman-crm-router-skill.git
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills/xiaoman-crm-router"
cp -R xiaoman-crm-router-skill/. "${CODEX_HOME:-$HOME/.codex}/skills/xiaoman-crm-router/"
```

重启 Codex 后，Skill 会自动识别提问中的“小满、Xiaoman、OKKI CRM、客户、跟进、线索、商机”等关键词。

## 配置

在运行 Codex 的终端或其启动环境中设置：

```bash
export XIAOMAN_BASE_URL="https://api-sandbox.xiaoman.cn"
export XIAOMAN_CLIENT_ID="your-client-id"
export XIAOMAN_CLIENT_SECRET="your-client-secret"
export XIAOMAN_SCOPE="company"
export XIAOMAN_TENANT_ID="your-crm-enterprise-profile"
```

如果要做线索、商机、订单和负责人分析，把 scope 按空格扩展，例如：

```bash
export XIAOMAN_SCOPE="company user lead opportunity invoices"
```

小满 API 对接需要主账号在“企业管理 → 外部对接 → API 对接”开通，并取得 `client_id`、`client_secret`。生产域名和租户权限请以管理员确认结果为准。

## 可以直接提问

- `找出 30 天没跟进的客户`
- `看客户 ABC 最近 90 天的跟进记录`
- `把所有客户提取成 Excel`
- `分析线索、商机和订单成交情况`

Skill 默认只读，不会自动新增、修改、删除客户或移入公海。

## 本地验证

运行时只依赖 Python 标准库：

```bash
python3 -m unittest discover -s tests -v
python3 scripts/run_router_eval.py evals/router_cases.jsonl
```

需要真实 API 配置后，才运行：

```bash
python3 scripts/xiaoman_client.py list-customers
```

## 目录

- `SKILL.md`：自动触发、路由和安全边界。
- `references/api-catalog.md`：接口、scope、字段关联和限制。
- `scripts/route_planner.py`：自然语言到调用计划。
- `scripts/route_executor.py`：计划执行、完整性、失败 ID、指标和导出。
- `scripts/xiaoman_client.py`：确定性 HTTP 适配器。
- `scripts/reflect_router.py`：脱敏轨迹和反馈晋级。
- `evals/router_cases.jsonl`：路由回归集。
- `docs/`：官方 API 调研和设计决策。

详细接口事实请以小满官方文档为准：<https://open.xiaoman.cn/>。
