# 插件平台服务与卡片合同

状态：2026-09-18，SDK 0.3.0。平台实现由 OpsMesh 的插件服务接口负责。

管理员批准 manifest 权限、绑定自动化后，为该安装签发有期限的 `omp_` 凭据。
该凭据只能访问 `/api/v1/plugin-runtime/{workspace_id}/{install_id}`，不能访问普通用户 API。
它不代表消息发送人的权限；平台通过已登记的外部身份绑定重新授权任务。
轮换、撤销、安装升级/停用或发布者公钥撤销后，旧凭据不能继续访问或读取流。

```python
from opsmesh_plugin_sdk.services import PluginServicesClient, StoreWrite

# http: caller-owned AsyncClient, HTTPS base_url ending /api/v1/, Bearer plugin token,
# explicit timeout (streaming read > 55 seconds). Never give the token to channel users.
host = PluginServicesClient(http, workspace_id, install_id)
configuration = await host.configuration()
connector = host.automation(automation_id)
accepted = await connector.submit(message)
saved = await host.write("delivery:123", StoreWrite(expected_revision=0, value={
    "event_id": str(accepted.id), "cursor": "0-0"
}))
async for frame in connector.events(accepted.id):
    # Deliver first; only persist a cursor after successful channel delivery.
    ...
```

权限：`messages.receive`、`messages.read`、`configuration.read`、`storage.read`、
`storage.write`、`permissions.read`、`logs.write`。manifest 声明不等于已获授权。
`permissions(PermissionQuery(...))` 返回发送人对指定资源的实际动作，仅供展示/预检查，
最终调用仍需重新授权。无法读取的资源返回空动作，不返回资源内容。

私有存储按工作区和安装隔离；每项最多 64 KB，每安装最多 512 项/2 MB。
创建使用 expected_revision=0，更新/删除使用当前 revision，冲突返回 409。
`values(prefix=..., offset=...)` 每页最多 100 项，用于进程重启后的恢复扫描。
完成的记录由插件按保留策略删除；配置只有管理员能修改，插件只能读取。
不提供 SQL、数据库连接、宿主机目录或平台密钥导出。配置只存非敏感值及环境变量引用，
渠道凭据由插件部署环境的 secret manager 提供。结构化日志经平台统一脱敏，不写原始消息正文。

`card.json` 用 `CardTemplate` 校验：channel、template_id、parameters、actions。
parameters 将厂商变量名映射为 title/text/status/event_id；不执行模板代码。
actions 的键对应厂商按钮回调标识，仅允许 pause/resume/cancel。
按钮不能授予权限、批准审批、修改工作流或选择任意 task_id。
插件必须验证回调来源，把卡片绑定到已接受 event_id 和原发送人，稳定地去重回调，
再通过普通消息入口提交控制动作。平台仍检查相同会话、发送人和实时 control 权限。
厂商卡片需要在其平台发布；此合同不是厂商卡片设计器的完整 JSON。

流式 `output.text` 是当前预览的替换文本；`output.completed` 是通过输出合同的最终结果。
工具事件只显示批准公开的名称和状态。插件负责节流更新、持久化游标、重连及投递失败恢复。
这套 SDK 不内置钉钉或其他渠道 SDK，也不自动运行第三方插件。
