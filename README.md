# OpsMesh Plugin Center

状态：2026-09-19。SDK 与插件统一维护的贡献仓库；平台负责安装、授权与执行策略。

```text
sdk/                         # 独立发布的 Python SDK
  src/opsmesh_plugin_sdk/
plugins/                     # 一个直接子目录一个插件
  dingtalk/
    plugin.json              # 能力、权限与版本声明
    pyproject.toml           # 插件独立依赖与命令入口
    src/opsmesh_dingtalk/     # 官方渠道适配与持久投递
    card-templates/task/v1/  # 卡片 UI、映射、预览数据
    deploy/                  # 部署文件与无密钥配置
    tests/                   # 产品流程
docs/                        # 架构、贡献、发布规范
.github/workflows/           # 统一门禁、按包发布
```

`opsmesh_plugin_sdk` 是 Python 导入名，不是插件中心的名字。
新插件通过 PR 增加 `plugins/<name>/`，不把业务代码合入 SDK，不导入 OpsMesh backend。
同仓库维护不表示平台 API/Worker 动态加载第三方代码；插件仍是独立进程。

开发：根目录执行 `uv sync --all-packages --all-extras --all-groups`。
参见 [SDK](sdk/README.md)、[钉钉插件](plugins/dingtalk/README.md)、
[架构](docs/architecture.md)、[开发与发布](docs/development.md)。

各包独立保留 Apache-2.0 许可证及历史声明。钉钉真实应用联调尚未验收。
