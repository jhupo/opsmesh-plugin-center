# SDK、插件仓库与平台分发边界

状态：2026-09-18。SDK 0.2.0 提供分发合同；平台下载实现验收状态以 OpsMesh 的
docs/plugin-distribution.md 为准。托管 OCI 执行及安装 Web UI 尚未实现。

## 所有权与目录

SDK 维护公共合同与客户端，平台维护目录信任、下载、审批及安装状态；业务插件独立仓库
维护 MCP/渠道服务及部署。SDK PR 合入 src/opsmesh_plugin_sdk，业务代码不合入 SDK。
公共插件目录应通过数据 PR 审核不可变索引，不执行插件代码；当前没有独立公共目录仓库。
平台 Marketplace 公共审核独立于工作区管理员批准的私有来源。

src/opsmesh_plugin_sdk 保持单层：contracts.py（消息与 manifest）、client.py（HTTPX）、
webhooks.py（HMAC）、packages.py（manifest 签名）、distribution.py（受签发布与目录）、
publish.py（发布 CLI）、__init__.py、py.typed。docs 维护架构与发布文档；
.github/workflows 提供 SDK ci/release 与外部插件 reusable plugin-release。

不增加 plugins 业务目录、运行时或数据库。SDK 不导入平台、不下载或运行代码。
执行固定为 remote，能力包括 mcp_server、skill、message_trigger、reply_channel。
无重启配置生效不表示动态 import Python 插件。

## 分发合同

SignedPluginRelease.release 包含 contract_version=1、SignedPluginPackage、
platform_requires/sdk_requires（packaging SpecifierSet）、license、source_repository、
source_commit；外层 Ed25519 签名保护这些字段，内层 manifest 签名仍独立验证。
PluginCatalog 包含 contract_version=1 与 entries（最多 200 项）；每项包含 plugin_key、
version、publisher_key_id、release_url、sha256、withdrawn。相同 key/version 不允许重复。

管理员审核目录 URL 和准确字节 SHA256；目录本身不能新增受信公钥。下载后的包必须同时
匹配目录身份/版本/发布者/摘要，并通过工作区已信任公钥验签、版本兼容及配置检查。
同版本内容不可覆盖。撤回阻止新安装；紧急停用使用既有 disable/撤销公钥接口。

目录与发布文件只包含 JSON。wheel/OCI 镜像若由作者发布，只用于其独立服务部署，
平台 API/Worker 不 pip install、不执行 setup.py、不解压运行第三方代码。

## 安装边界

平台分发入口复用 PluginService 安装及生命周期事务：固定目录同步→候选下载→验证→
权限/配置差异预览→管理员明确资源绑定与授权→原有安装服务→审计。
已有直接提交签名包、Marketplace 审核安装、enable/disable/switch_version/
retire_version/uninstall 保持各自用途，下载不能绕过公共目录审核或工作区授权。

声明权限不自动给 Agent 授权。资源须在该工作区预配置，凭据走平台 credential 引用。
升级授权使用 expected_generation；已登记版本通过 switch_version 回退，不能覆盖包。
旧版本资源保留原有绑定语义，卸载/退役仍检查依赖。私钥只留在发布环境。
发布步骤与 reusable workflow 参数见 [开发与发布](development.md)。
