# 小满 CRM Router Skill 设计

状态：设计已确认，第一版 Skill 已实现；真实租户连通性待配置后验证
日期：2026-11-10

## 理解摘要

- 创建一个给 Codex 使用、可自动发现的 `xiaoman-crm-router` Skill。
- 用户用自然语言提问，Skill 判断业务对象、动作、筛选条件和输出形式。
- Skill 按依赖关系组合小满 API，覆盖客户、联系人、跟进动态、线索、商机和订单查询。
- Skill 负责解释问题和组织结果；确定性脚本负责认证、分页、重试、响应校验和租户隔离。
- 第一版只读，不自动写入、删除、移入公海或修改小满数据。
- Skill 要越用越准确：自动记录路由轨迹、用户纠正和失败证据，提出候选改进并通过回归用例后采用。
- 凭据由本地环境变量提供，不进入 Skill 文件、日志或反思记录；每个运行 profile 必须提供 `tenant_id`。

## 假设

- Skill 默认安装在 `~/.codex/skills/xiaoman-crm-router/`，保持自动触发。
- 小满 API 以官方文档为准；接口路径、scope、生产域名和租户限额接入时再次核对。
- 用户的问题可能要求单客户精查，也可能要求跨客户的全量统计或导出。
- “没有用户投诉”不等于路由正确，只有明确反馈、可验证响应或回归用例才构成改进证据。

## 决策记录

| 决策 | 采用方案 | 放弃方案 | 原因 |
| --- | --- | --- | --- |
| 触发方式 | 自动识别自然语言 | 仅 `$xiaoman-crm` 显式调用 | 用户希望直接向 Codex 提问 |
| API 执行 | Skill + 确定性本地适配器 | 纯提示词拼接 HTTP | 将认证、分页、重试和错误处理集中到一个接口 |
| 自我优化 | 自动记录、提出候选、回归验证后采用 | 每次调用直接改核心规则 | 保留可追溯性，避免错误经验污染路由 |
| 默认副作用 | 只读 | 默认允许写入 | 分析和导出不应意外修改 CRM |
| 数据边界 | 每个 CRM 企业使用独立 profile 和租户标识 | 混用多个企业数据 | 小满官方要求企业数据隔离 |

## Skill 包结构

```text
xiaoman-crm-router/
├── SKILL.md
├── agents/openai.yaml
├── references/
│   ├── api-catalog.md
│   └── learned-cases.md
├── scripts/
│   ├── xiaoman_client.py
│   ├── route_planner.py
│   ├── route_executor.py
│   ├── run_router_eval.py
│   └── reflect_router.py
└── evals/
    └── router_cases.jsonl
```

`SKILL.md` 只放触发条件、路由主流程、只读边界和参考文件指针。`api-catalog.md` 保存接口、scope、字段关联和已知限制。`route_planner.py` 把自然语言转成最小调用计划，`route_executor.py` 消费计划并返回完整性、失败 ID 和确定性指标。`xiaoman_client.py` 是唯一 HTTP 适配器，提供 Token、列表分页、详情查询、跟进查询和规范化响应。`reflect_router.py` 负责脱敏记录、候选改进和评测。`learned-cases.md` 只接收通过评测的案例。

## 路由接口组合

| 用户意图 | 最小调用计划 |
| --- | --- |
| 客户列表、私海、公海、阶段筛选 | `company/list` 分页 |
| 客户画像、联系人、负责人 | `company/info`，必要时补 `user` |
| 单客户跟进时间线 | `company/info` → `dynamic/trail/list` |
| 长期未跟进客户 | `company/list` → 时间窗口内的 `dynamic/trail/list` → 按 ID 去重并计算沉默天数 |
| 线索到商机分析 | `lead/list`/`lead/info` → `opportunity/list` → 跟进动态 |
| 全量提取 | `company/list(all=1)` 分页 → 每条详情 → JSON/CSV/Excel |

路由器先抽取对象、动作、时间、筛选、输出和租户 profile，再选择最小调用集合。关联键为 `company_id`、`customer_id`、`lead_id`、`opportunity_id`、`user_id`。缺 scope、权限或 ID 时报告缺口，不猜测。

## 反思与评测

每次调用生成脱敏 `route_trace`：问题哈希、规范化意图、抽取参数、计划接口、实际顺序、分页数量、错误、空结果、结果完整性和用户纠正。反思器将证据分类为意图、接口、参数、关联、分析或表达错误，并生成候选案例。

回归集至少覆盖客户列表、客户画像、跟进时间线、长期未跟进、全量提取、线索转商机和权限不足。候选改进必须通过旧案例和新增案例，且不能扩大到写入或删除接口，才写入 `learned-cases.md`。核心路由规则保留版本和可回滚记录。

## 运行边界

- 凭据只从 `XIAOMAN_BASE_URL`、`XIAOMAN_CLIENT_ID`、`XIAOMAN_CLIENT_SECRET` 等本地配置读取。
- `401` 重新获取 Token；`403` 报告 scope 或 CRM 权限问题；参数错误不重试。
- `429`、`5xx`、超时使用有限退避重试；不伪造小满未公布的 QPS 限额。
- 分页处理至 `totalItem`，时间窗口重叠并按业务 ID 去重。
- 日志只保存接口、参数形状、状态码、数量和错误类型；联系方式、备注正文和 Token 默认脱敏。
- 结果必须显示数据范围、调用接口、完整性、失败数量和失败 ID。
- 导出支持 CSV、JSON 和 Excel-compatible XLSX；二进制 XLSX 以可交付的编码载荷返回。

## 落地阶段

1. 初始化 Skill 包、`openai.yaml` 和官方 API 参考。
2. 先用 mock 响应实现 API 适配器、分页、重试和规范化结果，并建立回归用例。
3. 实现自然语言路由和最小调用计划，验证单客户与全量分析两条主路径。
4. 加入 `route_trace`、反思器和候选案例验证。
5. 使用小满沙箱或脱敏租户做一次 Token、客户列表、详情和跟进动态连通性测试。
6. 运行 Skill 校验、路由回归和安全检查，确认文档、脚本和环境变量模板可复制给其他 Codex。

第一版已完成步骤 1–4，并通过 26 个 Python 行为测试、路由回归集和 Skill 格式校验。步骤 5 需要真实的 `XIAOMAN_*` 配置和测试租户，当前未执行生产 API 调用。

## 待接入时确认

- 生产还是沙箱 API 域名。
- API 账号可见范围：全部客户、私海、公海、归档客户。
- 需要的 scope：`company`，以及可选的 `lead`、`opportunity`、`invoices`、`user`、`webhook`。
- 结果输出格式和运行位置。
- 是否需要评论正文、邮件正文和附件内容。

官方 API 调研见 [xiaoman-api-research.md](./xiaoman-api-research.md)。
