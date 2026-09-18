# 开发与发布

状态：独立 SDK 仓库初始化，2026-09-18。

## 边界

本仓库是插件开发 SDK，不是插件中心服务端。服务端负责安装、审核、授权、工作区隔离、
事件持久化和执行；SDK 提供类型合同、同步/异步 HTTP 客户端、NDJSON 订阅、
Webhook 验签与可选 Ed25519 manifest 签名。具体渠道与业务插件在其他仓库实现。

代码从 OpsMesh 提交 8d9fc408 的 plugin_sdk 提取，初始公共 API 保持一致。
当前 OpsMesh 仍使用其 workspace 内的 SDK 包；本次初始化没有修改平台依赖。
待独立版本正式发布并验证后，平台应改为固定版本依赖，并删除其内置 SDK 源码，
避免后续两处分别维护。这个切换尚未执行。

## 本地开发

需要 Python 3.11+ 和 uv：

```sh
uv sync --extra signing
uv run ruff check .
uv run mypy
uv run python -m compileall -q src
uv build
uv run twine check --strict dist/*
```

src 布局避免仓库工作目录掩盖包安装缺失。发布包包含 py.typed 和许可证声明。
签名依赖为可选 extra，HTTP 通信与 Webhook HMAC 验签不依赖 cryptography。
不需要数据库、Redis、Docker 或 OpsMesh 后端源码即可安装和导入。

## 发布

CI 对 Python 3.11–3.14 做静态与打包检查。更新 pyproject.toml 版本及 uv.lock，
提交后推送对应 v 标签；发布工作流先通过同一套门禁，再校验标签和版本一致，
生成 wheel、源码包及 SHA256SUMS，上传 GitHub Release。

当前未配置 PyPI 自动发布，也未发布任何正式版本。使用本地构建 wheel：

```sh
pip install ./dist/opsmesh_plugin_sdk-0.1.0-py3-none-any.whl
# 需要 manifest 签名时
pip install './dist/opsmesh_plugin_sdk-0.1.0-py3-none-any.whl[signing]'
```

PyPI 发布需项目所有者后续配置可信发布身份；不要把长期令牌写进仓库。
所有迁入代码保留 Apache-2.0、NOTICE 和历史 MIT 声明。
