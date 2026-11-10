# 小满 Open API 官方文档核查

> 核查日期：2026-11-10。本文只引用小满开放平台官方文档（`open.xiaoman.cn`）。接口路径是文档中的相对路径；首页把 `https://api-sandbox.xiaoman.cn` 列为 API 域名。页面内容会更新，接入前应再次核对。

## 结论摘要

- 接入前要在小满主账号的“企业管理 → 外部对接 → API 对接”开通功能并取得 `client_id`、`client_secret`。认证接口是 OAuth2 风格的 `POST /v1/oauth2/access_token`，支持 `password` 和 `client_credentials`；刷新接口是 `POST /v1/oauth2/refresh_token`。
- 访问令牌按模块 `scope` 授权。官方示例列出 `company`（客户）、`lead`（线索）、`webhook`（消息推送）等 scope；只申请需要的模块，跨模块调用会返回无权限。
- 客户列表、客户详情、线索列表、线索详情和跟进动态均有 GET 接口；列表使用 `count` + `start_index` 分页，并返回 `totalItem`（客户列表另有 `count`）。官方页面没有公布最大页大小或数字限流/QPS/429 规则。
- 客户详情和线索详情提供负责人、状态、创建/更新时间以及联系人；跟进动态提供跟进类型、正文、关联客户/线索/商机、创建人和时间等。未发现单独命名为“操作历史”的 API，跟进动态列表是最接近的历史记录接口。
- Webhook 支持回调配置和按模块订阅 create/update/delete 事件；订阅功能仅对 Pro 版本开放，Smart 版本不支持。回调采用 HMAC-SHA256 签名校验 + AES-256-GCM 加密，失败重试 10s/30s/60s 三次后丢弃。
- 未在官方开放 API 菜单或已核对页面找到“导出客户/线索”接口或独立导出权限说明；不能把 CRM 页面导出权限推断为 API 权限。

## 1. 认证、授权与环境

### 开通与环境

官方快速开始要求先开通 API 对接，并从主账号的“企业管理 → 外部对接 → API 对接”查看 `client_id` 和 `client_secret`。页面列出 API 域名 `https://api-sandbox.xiaoman.cn`、UTF-8 编码、连接超时 60s、响应超时 60s；并说明当前 API 访问不会按 IP 做黑名单管控。[快速开始](https://open.xiaoman.cn/)

### 获取 token

`POST /v1/oauth2/access_token`，请求体为 `application/x-www-form-urlencoded`。官方文档列出的参数：

| 参数 | 说明 |
| --- | --- |
| `grant_type` | `password` 或 `client_credentials` |
| `client_id` | API 对接页取得 |
| `client_secret` | API 对接页取得 |
| `username` | 登录邮箱；`client_credentials` 时不用传 |
| `password` | 登录密码；文档说明需要 SHA-256 加密；`client_credentials` 时不用传 |
| `scope` | 以半角空格分隔的业务模块 scope |

文档说明 token 一般有效 8 小时（返回示例 `expires_in: 28800`）；`client_credentials` 模式没有 refresh token，应在过期前重新请求。示例响应包含 `token_type: Bearer`、`access_token` 和（password 模式）`refresh_token`。请求示例使用 `Authorization: {{access_token}}` 占位符；客户端应以实际租户测试结果确认是否需要显式拼接 `Bearer ` 前缀。[鉴权接口](https://open.xiaoman.cn/api-3473041)

最小请求示例（凭据必须由调用方安全注入，不要写入仓库）：

```bash
curl --location 'https://api-sandbox.xiaoman.cn/v1/oauth2/access_token' \
  --data-urlencode 'grant_type=client_credentials' \
  --data-urlencode 'client_id=YOUR_CLIENT_ID' \
  --data-urlencode 'client_secret=YOUR_CLIENT_SECRET' \
  --data-urlencode 'scope=company lead webhook'
```

### 刷新 token

`POST /v1/oauth2/refresh_token`，同样使用 `application/x-www-form-urlencoded`，参数为 `grant_type=refresh_token`、`refresh_token`、`client_id`、`client_secret`；成功返回新的 `access_token`、`refresh_token` 和 `expires_in`。文档列出“无效密钥”和“刷新令牌无效”两类 400 错误。[刷新令牌接口](https://open.xiaoman.cn/api-3483803)

### scope 与租户隔离

客户模块 scope 是 `company`，线索模块 scope 是 `lead`。鉴权文档说明 scope 只允许访问对应模块；例如只申请 `company` 时调用订单接口会报无权限。快速开始还明确要求按 CRM 企业隔离数据：多个小满 CRM 企业的数据不能混用，回传时也必须保留企业边界。[客户模块](https://open.xiaoman.cn/doc-338291) · [线索模块](https://open.xiaoman.cn/doc-338297) · [鉴权接口](https://open.xiaoman.cn/api-3473041) · [快速开始](https://open.xiaoman.cn/)

## 2. 客户、联系人与线索接口

### 客户列表

`GET /v1/company/list`，需要 `Authorization`。官方示例：

```text
/v1/company/list?count=20&start_index=1&removed=0&all=1&group_id=1&start_time=2022-09-21%2021%3A50%3A00&end_time=2022-09-23%2021%3A50%3A00&time_type=1
```

官方参数说明：

- `count`：每页数量，示例值 20。
- `start_index`：页码。
- `removed`：默认 0；设为 1 查询已删除数据列表。
- `all`：默认 1；`1` 查询所有客户，`0` 只查询私海客户，`2` 查询公海客户。
- `group_id`：客户分组 ID；值来自 `/v1/company/fields/selector?field=group_id`。
- `start_time`、`end_time`：时间范围。
- `time_type`：控制时间范围匹配字段；默认 1，`1` 更新时间、`2` 创建时间、`3` 建档时间。

响应为 `data.list`，列表项示例含 `company_id`、`user_id`、`name`、`short_name`、`serial_id`、`order_time`、`create_time`、`update_time`、`create_user`、`last_edit_user`、`archive_type`、`edit_time`；分页元数据为 `totalItem` 和 `count`。[客户列表](https://open.xiaoman.cn/api-3480070)

### 客户详情（含联系人）

`GET /v1/company/info`，通过 `company_id` 或 `serial_id` 查询；错误示例说明二者错误会返回 404 `Not Found Resource`。[客户详情](https://open.xiaoman.cn/api-3473043)

详情响应中已观察到的关键字段：

- 客户标识与时间：`company_id`、`serial_id`、`create_time`、`update_time`、`edit_time`、`order_time`、`archive_time`、`recent_follow_up_time`。
- 负责人/权限相关：`user_id`、`owner`、`last_owner`、`last_owner_info`（含 `user_id`、`name`、`nickname`）。
- 状态/阶段：`archive_type`、`public_type`、`trail_status`（`status_id`、`status_name`、`status_color`）、`trail_status_name`、`pool_id`、`pool_name`、`intention_level`、`star`。
- 联系人数组 `customers[]`：`customer_id`、`company_id`、`name`、`email`、`gender`、`remark`、`birth`、`tel_list`、`post_grade`、`post`、`contact[]`、`main_customer_flag` 及自定义字段 `external_field_data[]`。

文档还提供 `GET /v1/company/fields` 客户数据字典，用来发现标准/自定义字段及字段类型；阶段、分组、状态、地区、主营产品、来源等枚举可通过 `GET /v1/company/fields/selector` 查询。[客户数据字典](https://open.xiaoman.cn/api-3478270) · [客户字段枚举](https://open.xiaoman.cn/api-3478275)

### 联系人写入与列表边界

官方菜单提供 `POST /v1/company/push/customer`（页面标题仍标注“待修改”）以及 `POST /v1/company/pushCompanyAndCustomers`，后者可在客户写入时嵌套 `customers[]` 联系人并设置 `user_id`、`batch_user_ids`、`remove_user_id`。私海客户若传入的 `user_id` 不是跟进人，文档列出 404 `No Privilege`。[客户（含联系人）新增/编辑](https://open.xiaoman.cn/api-3478272) · [新增客户的联系人](https://open.xiaoman.cn/api-3484681)

已核对的官方菜单没有单独的“联系人列表 GET”；要取联系人，应先取客户详情的 `customers[]`（或在线索详情取 `customers[]`）。

### 线索列表与详情

线索模块 scope 为 `lead`。

`GET /v1/lead/list` 的官方示例：

```text
/v1/lead/list?start_index=1&count=10&start_time=undefined&end_time=undefined&email=&origin=undefined&sort_field=update_time&archive=
```

官方参数说明：`start_index` 第几页，默认 1；`count` 每页记录数，默认 10；`start_time`/`end_time` 是时间查询范围；`email` 可按邮箱搜索；`origin` 值来自 `/v1/company/fields/selector`；`sort_field` 支持 `update_time`（默认）、`order_time`（最近联系时间）、`edit_time`（最近编辑时间）；`archive` 为归档状态，`1` 已归档、`2` 已转化。响应示例为 `data.list` + `totalItem`，列表项含 `lead_id`、`name`、`short_name`、`serial_id`、`order_time`、`create_time`、`update_time`、`edit_time`。[线索列表](https://open.xiaoman.cn/api-3484688)

`GET /v1/lead/info` 支持 `lead_id` 或 `serial_id`。详情示例含 `user_id`、`owner[]`（`user_id`、`name`、`nickname`）、`status_name`、`status`、`archive_time`、`order_time`、`customers[]`（`customer_id`、`lead_id`、`email`、`tel_list`、`post`、`post_grade`、`main_customer_flag`、`contact` 等）。[线索数据查询](https://open.xiaoman.cn/api-3484689)

`GET /v1/lead/fields?type=lead` 返回线索/联系人的数据字典，可用于发现 `status`、`owner` 之外的标准和自定义字段。[线索|联系人的数据字典](https://open.xiaoman.cn/api-3484687)

## 3. 跟进记录与“操作历史”

### 跟进动态列表

`GET /v1/dynamic/trail/list`。可按 `company_id`、`lead_id`、`opportunity_id`、`start_time`、`end_time` 查询，并用 `count`、`start_index` 分页。官方示例：

```text
/v1/dynamic/trail/list?company_id=1&lead_id=1&opportunity_id=1&start_time=2022-09-21%2021%3A50%3A00&end_time=2022-09-23%2021%3A50%3A00&count=1&start_index=1
```

响应 `data.list[]` 已公开字段包括：

- 记录标识：`follow_up_id`、`trail_id`、`refer_id`、`client_id`。
- 类型/内容：`type`、`content`、`file_ids`、`comment_count`、`enable_flag`、`delete_flag`。
- 时间/操作者：`created_at`、`create_time`、`update_time`、`create_user`、`create_user_info`（`user_id`、`nickname`、`avatar`）。
- 关联对象：`company_id`、`customer_id[]`、`lead_id`、`lead_customer_id[]`、`opportunity_id`、`company_info`、`lead_info`、`opportunity_info`、`customer_info[]`、`lead_customer_info`、`file_info`。

示例中 `type` 为 101（快速记录）或 102（关联邮件备注）等。文档没有单独名为“操作历史/审计日志”的 endpoint；如果业务要做客户交互历史，`/v1/dynamic/trail/list` 是已公开的对应接口，但它不应被当作全量审计日志。[跟进动态查询接口](https://open.xiaoman.cn/api-3478244)

### 写入跟进动态

`POST /v1/dynamic/trail/push`，`company_id`、`lead_id`、`opportunity_id` 至少传一个；`content` 不能为空。`remark_type` 默认 101，官方列出的类型包含快速记录 101、关联邮件备注 102、电话 103、会面 104、社交平台 105、总部拜访 106、办事处拜访 107、来访总部 108、来访办事处 109、邮件 110、客户拜访 111、日程跟进 112。[提交跟进动态](https://open.xiaoman.cn/api-3484682)

## 4. 分页、增量同步与限流

### 分页与增量拉取

客户、线索、跟进列表都使用页码式分页：`start_index` + `count`。客户列表支持按更新时间/创建时间/建档时间过滤；线索列表支持开始/结束日期、邮箱、来源、排序字段；跟进列表支持对象 ID 和时间范围。列表响应带 `totalItem`，因此可循环至 `start_index * count >= totalItem`；实现时应处理空列表和时间边界重复（按 ID/更新时间去重）。

文档示例没有给出最大 `count`、稳定排序保证、游标或 `updated_since` 专用参数。若要可靠增量同步，优先使用时间窗口 + ID 去重，并把删除事件纳入 Webhook（见下节），不要假设分页结果天然是快照。

### Webhook 增量事件

消息订阅流程页面说明该功能仅 Pro 版本开放，Smart 版本暂不支持。[消息订阅流程](https://open.xiaoman.cn/doc-338308)

回调配置：

- `POST /v1/webhook` 创建，Body `{ "callback_url": "https://example.com/callback" }`；返回 `security_method` 和 `security_config`。[创建回调配置](https://open.xiaoman.cn/api-3497011)
- `GET /v1/webhook` 获取，返回 `callback_url`、`callback_verify`、`security_method`（示例为 `AES-256-GCM`）。[获取回调配置](https://open.xiaoman.cn/api-3497057)
- `PUT /v1/webhook` 修改 callback URL。[修改回调配置](https://open.xiaoman.cn/api-3497056)
- `POST /v1/webhook/regenerate-secret` 重新生成 webhook secret。[重新生成加密密钥](https://open.xiaoman.cn/api-3497059)

订阅配置：

- `POST /v1/subscribe` 创建，`subscribe_type` 指定模块，`subscribe_configs[]` 指定事件；官方特别说明一次只能订阅一个模块，但一个模块可同时订阅多个事件。[创建订阅配置](https://open.xiaoman.cn/api-3497012)
- `PUT /v1/subscribe/{subscribe_type}` 修改。[修改订阅配置](https://open.xiaoman.cn/api-3497054)
- `GET /v1/subscribe/{subscribe_type}` 获取详情；`GET /v1/subscribe` 获取列表；`DELETE /v1/subscribe/{subscribe_type}` 删除。[获取订阅详情](https://open.xiaoman.cn/api-3497060) · [获取订阅列表](https://open.xiaoman.cn/api-3497061) · [删除订阅配置](https://open.xiaoman.cn/api-3497055)

与客户/线索/跟进相关的官方事件：

| `subscribe_type` | 事件 | 文档列出的返回字段 |
| --- | --- | --- |
| `crm.company` | `xiaoman.crm.company.create/update/delete` | `company_id`, `serial_id` |
| `crm.customer` | `xiaoman.crm.customer.create/update/delete` | `customer_id` |
| `crm.lead` | `xiaoman.crm.lead.create/update/delete` | `lead_id`, `serial_id` |
| `crm.dynamic_trail` | `xiaoman.crm.dynamic_trail.create/update/delete` | `trail_id` |

这些表格是事件返回字段清单，不是完整对象 schema；实现上应把事件 ID 当作增量触发器，再调用详情接口补齐对象（这是基于官方“返回字段”表和详情 API 的工程推断）。[创建订阅配置](https://open.xiaoman.cn/api-3497012)

### 回调验签、加密与重试

“测试回调接口”页面说明：回调请求 Header 包含 `X-Signature` 和 `X-Timestamp`，Body 为 `{"message_id":"msg_xxx","data":"加密内容"}`；签名算法是 HMAC-SHA256，使用 `X-Timestamp` + Body 的 `data` 和创建回调配置返回的 `security_config` 做校验；解密使用 AES-256-GCM。测试响应必须带回相同的 `message_id`，并返回测试所需的 `biz_data`。[测试回调接口](https://open.xiaoman.cn/api-3497013)

创建回调配置页另有生产回调约定：消息推送后响应必须包含 `{"data":{"message_id":xxxxx}}`；失败按 10s、30s、60s 重试，三次失败丢弃消息。[创建回调配置](https://open.xiaoman.cn/api-3497011)

### 限流状态

在本次核对的官方首页、认证、客户、线索、跟进、Webhook 页面中，未找到数字化的 QPS、每分钟配额、最大 `count`、`429` 响应或 `Retry-After` 约定。能确认的运行约束只有首页的 60s 连接/响应超时和“不会对 IP 进行黑名单管控”。因此接入方应实现指数退避、超时重试和对 429/5xx 的通用处理，但不要把自设阈值写成小满官方限流值；上线前应向小满对接渠道确认租户级配额。

## 5. 导出权限与数据安全边界

- 官方开放 API 导航列出客户/线索列表、详情、字段字典、写入、跟进和消息推送等接口，但本次核对未发现客户/联系人/线索“导出” endpoint，也未发现独立的导出 scope 或权限字段。CRM Web UI 的导出能力不能据此推断为 Open API 能力。
- `scope` 是第一层隔离：只申请业务所需模块；`company`、`lead`、`webhook` 等 scope 不能互相替代。[鉴权接口](https://open.xiaoman.cn/api-3473041)
- 企业是第二层隔离：官方要求不同 CRM 企业的数据严格分开，回传时也要保留企业映射。[快速开始](https://open.xiaoman.cn/)
- 对私海客户写入时，`user_id` 必须是该客户跟进人，否则客户写入接口返回 404 `No Privilege`。[客户（含联系人）新增/编辑](https://open.xiaoman.cn/api-3478272)
- Webhook 载荷受签名和加密保护；应安全保管 `security_config`/webhook secret，收到回调先验签和解密，再按 `message_id` 做幂等。[测试回调接口](https://open.xiaoman.cn/api-3497013) · [重新生成加密密钥](https://open.xiaoman.cn/api-3497059)
- 官方示例页面内含演示 token/手机号/邮箱等样例值；这些是文档样例，不应复制到生产配置、日志或仓库。

## 6. 最小接入清单（按官方能力映射）

1. 在主账号开通 API 对接，安全保存 `client_id`/`client_secret`。
2. 申请最小 scope：客户同步至少 `company`，线索同步至少 `lead`，Webhook 订阅增加 `webhook`。
3. 获取 token，按 `count`/`start_index` 分页拉取列表；客户和线索用时间窗口增量并以 ID 去重。
4. 以客户详情 `/v1/company/info` 或线索详情 `/v1/lead/info` 补齐联系人、负责人、状态和自定义字段。
5. 以 `/v1/dynamic/trail/list` 拉取跟进历史；若租户是 Pro，创建 `/v1/webhook`、订阅 `crm.company`/`crm.customer`/`crm.lead`/`crm.dynamic_trail` 的 create/update/delete 事件。
6. 回调端实现 HMAC-SHA256 验签、AES-256-GCM 解密、`message_id` 幂等和 10s/30s/60s 重试窗口内的快速确认。
7. 对导出、最大页大小、限流配额、生产域名等未在公开文档确认的事项，向小满官方对接渠道获取租户级书面确认。
