# OpsMesh Plugin SDK

状态：2026-09-20，0.5.0 源码版本。Python 3.11+，Apache-2.0。
SDK 0.4.1 已发布；0.5.0 的发布状态以 GitHub Release 为准。

```text
src/opsmesh_plugin_sdk/
├── client.py                # PluginClient 组合入口
├── context.py               # 安装与受委托用户身份
├── services/
│   ├── identity.py          # 实际权限、用户身份
│   ├── resources.py         # 已授权资源发现
│   ├── knowledge.py         # 知识检索、版本化记忆
│   ├── storage.py           # 插件私有 KV
│   ├── configuration.py     # 安装配置
│   └── observability.py     # 结构化日志
├── messaging/
│   ├── contracts.py         # 消息、流、附件、审批
│   ├── client.py            # 持久任务入口、状态、控制、流
│   └── webhooks.py          # 中立 webhook 签名
└── packaging/
    ├── manifest.py          # 能力与权限声明
    ├── packages.py          # 包签名
    ├── distribution.py      # 发布描述与目录
    └── publish.py           # 发布者签名命令
```

合同与客户端按功能内聚，不为每个模型/方法建立文件。
执行复用 messaging 自动化入口，没有平行执行框架或空的 execution 包。
调用者拥有 HTTPX 认证、生命周期和重试策略；流式读超时须超过平台正常轮换周期。
写操作遵循幂等键/CAS 合同，不自动重试所有 POST。

不依赖 OpsMesh 源码、数据库驱动、渠道 SDK 或卡片模板。
安装凭据不是用户权限；平台始终验证租户、安装、批准权限与真实用户授权。
参考 [服务与示例](../docs/services.md)、[架构](../docs/architecture.md)、
[独立发布规范](../docs/development.md)。

仓库根运行 uv build --package opsmesh-plugin-sdk。
生产安装发布 wheel；平台开发 PR 可固定独立仓库完整提交，不能使用源码复制或路径回退。
