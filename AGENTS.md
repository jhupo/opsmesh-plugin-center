# OpsMesh Plugin SDK 开发规范

状态：2026-09-18。修改前阅读 README.md、docs/architecture.md 和 docs/development.md。

## 仓库与所有权

- 本仓库只拥有 Apache-2.0 Python SDK；插件中心服务端在 OpsMesh，渠道/业务插件各自独立仓库。
- 外部 PR 可以贡献 SDK 公共合同、客户端和文档；业务插件代码不得合入 src、SDK 依赖或 Actions。
- 不设置自动扫描/加载第三方插件的 plugins 目录。插件安装不能执行 setup.py 或动态 import。
- 合同以 src/opsmesh_plugin_sdk 为唯一维护源；平台通过不可变发布版本或提交归档安装，不复制源码。
- 保持单层包。只有独立生命周期、稳定协议或可替换实现才增加子包。
- 禁止兼容性别名、重导出 shim、静默回退、为拆分而拆分的转发模块。

## 依赖和安全

- 仅依赖 HTTPX、Pydantic、packaging 和可选 cryptography，优先复用公开接口。
- 不引入 backend、数据库、Worker、Agent SDK、Docker 或渠道厂商的依赖。
- Ed25519 的 cryptography 必须在 signing extra 内，基础导入不能强制加载它。
- 调用者负责 HTTP 客户端生命周期、身份验证、超时、网络重试、持久化去重及渠道投递。
- 不记录 token、签名私钥、原始用户数据和工具参数；外部 sender 信息不是平台授权身份。
- 插件安装凭据与用户身份分离；services 只能使用安装范围内的接口，不能伪装平台用户。
- cards 是数据合同，不嵌入厂商 SDK；按钮必须复用消息授权入口，不能直接批准审批。
- 下载、目录信任、安装授权和运行时策略属于平台；SDK 不自行拉取和执行远程代码。

## 校验与交付

- 组织重构只运行 Ruff、strict mypy、编译、wheel/sdist 元数据与独立安装检查。
- 行为变化只维护连接器流程测试，覆盖入站→平台响应/流式→验签/交付，以及流程中的
  拒绝、断线恢复、去重和脱敏。不为单文件、类、序列化器或 helper 单独建测试。
- 禁止为本次改动临时写一批单点测试再删除；不把一次 mock HTTP 请求称作平台端到端验收。
- 依赖用 uv.lock 锁定；库使用者由 pyproject.toml 获取运行依赖，不依赖本仓库开发环境。
- README 与 docs 各有唯一职责，不新增重复路线图和永久保存的生成快照。
- 发布须校验 tag、包版本和 master 归属。门禁后仅构建一次，发布复用同一 artifact；
  固定 Action SHA，按 job 分配最小权限，PR 不使用私钥或发布权限。
- SDK 发布与插件发布是不同流水线。未配置 PyPI Trusted Publisher 前不宣称支持 PyPI 自动发布。
- 保留 Apache LICENSE、NOTICE 与适用的历史 MIT 声明；不得把 LGPL 平台实现搬入 SDK。
- 每个完成的功能点单独提交；不打正式 tag，除非用户明确要求发布。
