# SDK、插件仓库与平台分发边界

状态：2026-09-18。本文分别标明当前实现与待实现设计，不把设计视为可用功能。

## 所有权与目录

| 仓库 | 内容 | 外部贡献位置 |
| --- | --- | --- |
| opsmesh-plugin-sdk-python（当前） | Python 公共协议和客户端 | SDK PR 合入 src/opsmesh_plugin_sdk；文档合入 docs |
| OpsMesh（当前） | Marketplace、插件安装授权、持久化与运行管理 | 平台领域代码和平台接入流程 |
| 每个插件的独立仓库 | 渠道身份校验、业务工具、MCP 服务、插件部署 | 插件作者自己的 src 与发布流程 |
| 插件目录仓库（待建） | 经审核的索引、发布者身份、不可变资产引用 | 提交数据 PR，不提交业务实现或私钥 |

SDK 不作为插件实现的 monorepo，不在其中创建空 plugins、marketplace、runtime 或各渠道目录。
外部插件可以在目录中登记，但不进入 SDK 依赖，也不执行第三方仓库的代码来生成索引。

```text
opsmesh-plugin-sdk-python/
├── src/opsmesh_plugin_sdk/
│   ├── contracts.py     # 消息、回复、流式帧、manifest
│   ├── client.py        # HTTPX 同步/异步客户端
│   ├── webhooks.py      # HMAC 验签和作用域校验
│   ├── packages.py      # Ed25519 manifest 签名
│   ├── __init__.py
│   └── py.typed
├── docs/
│   ├── architecture.md  # 边界、插件目录和平台获取合同
│   └── development.md   # SDK 开发与实际发布流水线
├── .github/workflows/   # ci.yml、release.yml
├── pyproject.toml
├── uv.lock
├── README.md
├── AGENTS.md
└── LICENSE / LICENSE-MIT / NOTICE
```

当前 5 个实现模块已经有明确职责，暂不再拆 transport/models/security 等小型子包。
后续确有第二种稳定传输或独立生命周期时再拆分。流程测试按行为增长，不为模块凑测试目录。

## 当前平台怎样安装插件

当前 PluginManifest 只允许 execution=remote，支持 mcp_server、skill、message_trigger、
reply_channel。SignedPluginPackage 是签名 JSON，不是 wheel、Docker 镜像或压缩源码。

已有两条入口：
- Workspace 管理员向 /api/v1/workspaces/{workspace_id}/plugins 提交 package、
  bindings、approved_permissions；升级还要 expected_generation。
- Marketplace 已有 listing_type=plugin，可发布/审核目录项；安装读取目录项中的签名
  manifest，并调用同一个 PluginService。公共目录需审核，私有目录遵守工作区边界。

平台验证受信发布者公钥、插件身份、签名、权限集合、资源作用域和配置 Schema，持久化
不可变 release、资源绑定与审计。已有 enable/disable/switch_version/retire_version/uninstall。
插件服务必须已由发布者或管理员部署；MCP/回复 URL 来自管理员配置的工作区资源，
不会从任意下载文件中直接获取执行权限。配置无重启生效不等于第三方 Python 模块热加载。

**当前没有 GitHub URL 拉取器、外部目录同步器、自动部署插件进程或 OCI 拉取安装。**
SDK 的安装与平台的插件安装是两条独立链路，pip 安装 SDK 不会安装任何业务插件。

## 外部插件发布标准（设计，尚无通用插件流水线实现）

一个插件一个 repo；建议 src/<plugin_package>、plugin/manifest.json、docs、Dockerfile
（仅服务型插件需要）、.github/workflows。不要把平台源码或 SDK 源码复制进去。

- 插件 key 是稳定身份，版本独立于 SDK；当前 manifest 只接受 X.Y.Z 正式版本。
- manifest 不含工作区 ID、安装令牌、用户信息、凭据和私钥。
- 发布前验证 manifest、最小权限和接入流程，再构建并签名；PR 无法读取签名 secret。
- 必备资产：签名 JSON 包和 SHA256SUMS；服务型插件另发布固定 digest 的 OCI image。
  Python wheel 可选，只用于插件自己的部署环境，平台 API/Worker 不 pip install 插件。
- Ed25519 签名证明受信发布者认可 manifest；SHA256 证明下载字节一致；
  GitHub provenance 证明构建来源。这三者用途不同，不相互替代。
- 当前签名 manifest 不含 OCI digest、SDK 范围、远程资产 URL；不能假装这些字段已经受签。
  将来增加需更新 SDK 合同和平台消费者，并定义受签 release descriptor，再开放托管执行。
- 发布者私钥只在自己的受控发布环境，平台持有管理员信任的公钥；目录不能自授信。
- 插件升级显式授权，权限扩大重新审批，不自动跟随 latest。
- 外部插件许可证由其作者声明，使用 Apache SDK 本身不要求闭源插件公开源码。

## 平台自动拉取设计（待实现）

复用既有 Marketplace + PluginService，不新建第二套安装状态机：
审核过的目录索引 → 固定版本候选 → 下载到暂存 → 验证摘要/身份/签名 →
展示权限及配置差异 → 管理员授权资源绑定 → 现有安装事务 → 激活与审计。

目录数据拟包含 plugin_key、version、publisher_key_id、仓库身份、固定 commit/tag、
manifest URL/SHA256、兼容范围、许可证和撤回状态。索引本身须经过平台信任的
目录签名或审核，插件签名仍独立校验。没有可信来源时拒绝拉取。

下载由独立后台步骤完成，不在安装数据库事务内做网络 I/O。仅允许已配置来源的 HTTPS，
拒绝 URL 凭据、私网/回环/元数据地址；重定向逐跳重新校验，限制跳数、超时和下载体积。
先落内容寻址缓存再交给安装服务；身份/版本/摘要不一致拒绝，下载失败不改变当前版本。
同 key/version 不可覆盖，etag 只是缓存提示，不是信任证据。

当前 remote 插件不下载可执行代码。未来托管插件仅由 Runtime 拉取固定 OCI digest，
执行网络/文件/资源策略；API/Worker 不接触 Docker socket，不动态 import。
发布或拉取不自动授权，卸载有引用时仍拒绝；在途任务按冻结 release 运行，
撤销公钥/禁用插件按既有执行前授权检查阻止后续副作用。

## 后续验收边界

1. 已有：SDK 类型合同、HTTP/流式、验签；平台签名包安装、目录审核、生命周期与资源绑定。
2. 本次规范化：独立 SDK 源码 owner、CI 单次构建与 tag 复用资产、文档与贡献位置。
3. 尚未实现：外部目录索引及同步、受控下载器、兼容性字段、托管 OCI 插件运行、
   发布者密钥轮换运营流程、插件安装 Web UI。
4. 新增拉取功能时复用平台流程测试，覆盖下载/验签拒绝、跨工作区、重复安装、
   升级权限扩大、撤回/回滚及输出；不为每个下载 helper 单独建测试文件。
