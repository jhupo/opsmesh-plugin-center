# Plugin Center 开发规范

状态：2026-09-19。修改前阅读 README.md、docs/architecture.md、docs/development.md。

- SDK 唯一源码在 sdk/src/opsmesh_plugin_sdk；一个插件一个 plugins/<name> 目录。
- 各包独立版本、依赖、许可证、入口和分发产物。根 uv workspace 只服务开发。
- SDK 不导入插件，插件不互相导入。不复制 SDK 源码、不修改 sys.path。
- 插件的 manifest、模板、部署资料、产品流程在自己的目录，Actions 在根 .github。
- SDK 拥有厂商无关合同与 HTTP 客户端；渠道通信复用官方 SDK。
- 平台拥有信任、安装、权限、审批与生命周期；这里不导入 backend。
- 同仓库维护不表示 API/Worker 动态 import；插件独立部署运行。
- 模板 UI、数据映射和预览样例分离；不得以变量映射冒充厂商原生模板。
- 禁止兼容性 shim、静默回退、重复协议实现、单行转发层。
- 不记录密钥或用户正文；安装凭据不是用户身份，卡片按钮不能绕过审批。
- 组织重构只做静态、导入及打包检查。行为变化扩展已有产品流程，不写单点测试。
- PR 不使用发布密钥；SDK/各插件独立 tag，门禁后复用构建产物，发布禁止覆盖。
- 完成功能点即提交；未授权不打正式 tag、不发送真实渠道消息。
- 各包保留许可证与第三方声明，不将 LGPL 平台代码复制到 Apache 包。
