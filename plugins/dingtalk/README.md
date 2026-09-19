# OpsMesh DingTalk plugin

状态：2026-09-19，开发验证中；尚未用真实钉钉应用验收。

独立部署的渠道插件，通过官方 DingTalk Stream SDK 接收机器人消息/卡片回调，
通过官方 OpenAPI SDK 更新卡片，通过 OpsMesh Plugin SDK 提交消息并读取任务流。
平台不加载本仓库代码。卡片只投递给原发送人，不向群成员公开结果，不允许转发。

配置要求：`OPSMESH_URL`（HTTPS 且以 /api/v1/ 结尾）、`OPSMESH_WORKSPACE_ID`、
`OPSMESH_INSTALL_ID`、`OPSMESH_PLUGIN_TOKEN`、`DINGTALK_CLIENT_ID`、`DINGTALK_CLIENT_SECRET`。
密钥只放部署环境。插件安装配置提供 automation_id、corp_id、contract_version 和 card。
用户以 `corp_id:staff_id` 绑定到平台成员；用户昵称、级别及正文都不能授予权限。

仓库根安装：`uv sync --locked --all-packages --all-extras --all-groups`；运行：`uv run opsmesh-dingtalk`。
部署配置见 deploy/configuration.example.json 和 deploy/env.example；密钥不得提交。
官方卡片模板必须先在钉钉开发者平台发布；card-templates/task/v1/card.json 保存 UI 组件树，mapping.json 保存变量/按钮映射，
preview.json 保存预览数据；UI 导入后需在设计器编译、预览并发布，当前尚未真实验收。按钮只支持 pause/resume/cancel，不支持审批。

运行时使用安装专属的有界平台存储，不连接平台数据库。持久化消息后才确认回调，
任务和卡片使用稳定 ID，失败保留并重试，进程重启从持久化记录恢复。
正式发布前仍需真实钉钉应用、已发布模板、两个映射用户及受控测试会话验收。

## 安装与配置

1. 在 OpsMesh 创建并发布工作流、团队及 message 自动化；输入合同包含 question 字符串和
   user 对象，model_input_fields 只开放 question。按需要允许 pause/resume/cancel，
   公开输出节点和安全工具状态；日志专家、知识与记忆由该工作流编排，插件不硬编码业务。
2. 将每个 `corp_id:staff_id` 绑定到真实平台成员；分别授予自动化、团队、专家、工作流以及
   工具/知识/记忆的必要权限。按钮操作另外需要相关资源的 control 权限。
3. 用 OpsMesh SDK 的 sign_package 为 plugin.json 签名；管理员登记精确插件 key 的发布者
   公钥，把 receive 绑定到自动化 ID，并批准 manifest 中的权限。私钥不传到平台。
4. 管理员向 `/workspaces/{ws}/plugins/{install}/configuration` PUT
   `{"expected_revision":0,"value":{"automation_id":"实际 UUID","corp_id":"实际企业 ID",
   "contract_version":1,"card":{...mapping.json 的实际内容...}}}`。
   不把渠道密钥写入这个配置；密钥通过前述环境变量或部署 secret manager 提供。
5. POST `/workspaces/{ws}/plugins/{install}/credentials`，明确 permissions 和 lifetime_hours，
   将返回一次的 token 安全交给插件进程。轮换立即撤销旧 token，安装 generation 改变后重新签发。
6. 钉钉企业内部应用启用 Stream 机器人及卡片回调，授权卡片创建/投放/更新，发布自己的卡片模板。
   模板变量对应 card-templates/task/v1/mapping.json 的 parameters；按钮服务端回调的
   `content.cardPrivateData.params.action` 分别设置 pause/resume/cancel。
   不从回调参数读取平台用户 ID、任务 ID、角色或审批结果。

正文只支持文本；附件/图片不会被当作可执行指令。群内触发会转入原员工与机器人的单聊卡片，
不在群里广播日志或答案。需要机器人能联系该员工。审批提示引导用户回 OpsMesh 完成授权操作。

## 恢复与运行边界

消息 event_id、卡片 outTrackId 稳定；重复消息不会产生新任务。每条投递有 120 秒 CAS 租约，
每轮操作限时 90 秒；成功投递后才推进流游标。断线使用持久游标和最终状态恢复。
每轮聚合一批文本和工具状态再更新卡片，默认每 3 秒扫描，避免逐 token 发 API。
失败退避至最多 300 秒，连续 12 次进入 blocked；记录保留，不能当作成功。管理员排查后，
可用 PluginServicesClient 读取对应 `card:<digest>`，CAS 更新 blocked=false、attempts=0、
retry_at=0（确认 lease_until 已过期），恢复时仍会重新授权。完整投递的记录按 retention_hours 清理，
默认 24 小时；私有存储受平台 512 项/2 MB 限额约束，不适合无限囤积历史消息。
已发出的内容不能追溯收回；撤权阻止后续获取和发送新结果。

官方 Stream 0.24.3 部分同步请求没有 timeout，并会捕获取消信号，因此入口用受监督子进程：
35 秒无事件循环心跳便终止并重启，最多自动重启 3 次，耗尽后退出供部署系统告警。
卡片与 OAuth 使用官方 OpenAPI SDK 的异步调用、5 秒连接/15 秒读取超时及有限重试。
没有复制 HTTP 协议或 monkeypatch SDK。SDK 日志过滤为事件代码，禁止打印响应正文和 ticket。

## 验证与发布

根目录 CI 按 plugins/dingtalk/pyproject.toml 运行静态检查、现有产品流程和独立包构建。
仓库只有一个连接器产品流程测试，平台/钉钉服务在其中模拟；不声称它是真实钉钉端到端验收。
OpsMesh 仓库另有真实 API/Worker/PostgreSQL 的插件入站与双身份授权流程。
根 CI 构建各包 wheel/sdist；plugins/dingtalk/vX.Y.Z 经门禁后签名，上传同一次构建的包及证明。
发布需配置 OPSMESH_PLUGIN_SIGNING_KEY，尚未执行正式发布或发布 Docker 镜像。
deploy/Dockerfile 供运营者从仓库根 dist 中的 SDK 与插件 wheel 构建独立进程镜像；平台不会自动启动该镜像。

依赖来自官方 [Stream SDK](https://github.com/open-dingtalk/dingtalk-stream-sdk-python)
和 [OpenAPI SDK](https://github.com/aliyun/alibabacloud-sdk)。
遵守 [Apache-2.0](LICENSE)，不包含平台源码。
