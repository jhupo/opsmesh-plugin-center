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
    card-templates/          # task/approval/result 各自 v1 UI、映射和预览
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
当前开发版本为 SDK 0.4.0、钉钉插件 0.2.0；支持媒体输入、群指定接收人、卡片内审批。
发布流程包含独立 Python 包、固定摘要镜像及受签 descriptor v2；未执行正式发布。
2026-09-20：插件中心已推送至 `jhupo/opsmesh-plugin-sdk-python`，保留现有远程名称。
SDK 0.4.0 已由 GitHub Actions 发布，OpsMesh 已固定发布 wheel 与 SHA-256；
钉钉 0.2.0 的签名密钥配置、镜像发布和真实渠道验收仍待完成。
