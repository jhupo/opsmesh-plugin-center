# 插件平台服务

状态：2026-09-20，SDK 0.5.0 源码合同；正式发布与平台部署独立验收。

SDK 按 services、messaging、packaging 分类。PluginClient 组合功能客户端，
调用者管理 HTTPX 连接、安装凭据和超时；不自建 HTTP、重试或数据库驱动。
服务地址为 /api/v1/plugin-runtime/{workspace_id}/{install_id}。

```python
from opsmesh_plugin_sdk.client import PluginClient
from opsmesh_plugin_sdk.context import UserContext
from opsmesh_plugin_sdk.services.resources import ResourceQuery
from opsmesh_plugin_sdk.services.storage import StoreWrite

host = PluginClient(http, workspace_id, install_id)
context = UserContext(automation_id=automation_id, sender_id=verified_sender_id)
identity = await host.identity.resolve(context)
teams = await host.resources.list(ResourceQuery(
    **context.model_dump(), resource_kind="team", action="invoke",
))
configuration = await host.configuration.read()
accepted = await host.automation(automation_id).submit(message)
saved = await host.storage.write("delivery:123", StoreWrite(
    expected_revision=0, value={"event_id": str(accepted.id), "cursor": "0-0"},
))
async for frame in host.automation(automation_id).events(accepted.id):
    # 渠道投递成功后才保存游标；失败不应跳过消息。
    ...
```

| SDK 入口 | 权限 | 行为 |
| --- | --- | --- |
| identity.context | 有效安装凭据 | 当前安装、工作区及实际批准的服务权限 |
| identity.resolve | identity.read | 已绑定发送人的平台 ID 和显示名，不返回用户目录或邮箱 |
| identity.permissions | permissions.read | 指定资源的有效操作；不可读资源返回空动作 |
| resources.list | resources.read | 分页发现可读/可调用的团队、专家、项目、工具、MCP、技能、工作流、文件、知识、记忆和自动化；只返回 ID、名称和有效动作 |
| knowledge.search | knowledge.read | 复用平台检索，返回用户可见的语义记忆/知识引用和片段 |
| knowledge.remember | memory.write | 复用语义记忆版本服务；平台校验作用域写权限、资源所有权及 CAS |
| storage.read/values | storage.read | 插件安装私有 KV 查询 |
| storage.write/delete | storage.write | 插件安装私有 KV CAS 写入/删除 |
| configuration.read | configuration.read | 安装配置只读，不能导出平台密钥 |
| observability.log | logs.write | 脱敏结构化运行日志；审计只记录接收事实，不把插件内容作为平台可信审计 |
| automation(...).submit | messages.receive | 已批准入口持久受理工作；也提交 follow_up/pause/resume/cancel |
| automation(...).state/events | messages.read | 安装来源隔离的状态和 NDJSON 流 |
| messages.decide_approval | approvals.decide | 真实任务审批、实时用户校验及幂等决策 |
| messages.upload_attachment | attachments.write | 用户授权的消息附件上传、摘要及幂等引用 |

权限必须同时满足 manifest 声明、管理员批准、安装凭据及实时用户资源授权。
外部 sender 必须经渠道验证并已绑定平台成员；昵称、级别和插件自报角色不授予权限。
身份、资源、知识和记忆接口均要求当前 release 绑定的自动化，不能借其他入口冒充用户。
资源列表只是发现，不证明运行环境可用，也不替代执行时再次授权。检索不隐式调用收费模型。
知识与记忆是参考数据，插件不能把其中内容当作系统指令。

团队、专家、工具和 MCP 执行继续经用户配置的自动化/工作流及平台工具网关。
SDK 不提供绕过任务、审批、预算和隔离策略的直接工具执行端点；不复制任务执行器。
管理员配置 API 不向安装凭据开放。

私有存储每项 64 KB，每安装 512 项/2 MB；创建 expected_revision=0，
更新/删除须匹配版本，冲突 409。列表每页 100 项，配置保留键不可由插件写入。
插件自行清理过期投递数据。不提供 SQL、平台数据库连接、无限对象存储或宿主机文件访问。
附件最多 20 MiB，仍受平台更小配额限制；external_event_id + slot 去重。
凭据轮换、撤销、安装停用或发布者失信后，后续请求拒绝。

卡片模板、变量映射、长度限制和渠道回调属于 plugins/<name>/，SDK 不含 cards.py。
平台只提供消息、输出和审批合同，不再发布卡片模板 schema。钉钉模板校验在插件
scripts/check_assets.py；JSON 校验和模拟流程不代表真实钉钉设计器/渠道验收。

0.5 直接迁移旧根 contracts/services/cards/packages/distribution/webhooks 模块
及 PluginServicesClient，没有旧路径重导出或兼容包装。
