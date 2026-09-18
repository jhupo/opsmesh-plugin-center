# 开发与发布

状态：2026-09-18；GitHub Actions 已配置，正式 tag/PyPI 发布尚未执行。

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

运行依赖仅 HTTPX/Pydantic，Ed25519 签名使用 signing extra。
src 布局要求先安装 SDK；不得把父仓库或 backend 加到 PYTHONPATH 来掩盖安装错误。
构建产物包含 py.typed、Apache LICENSE、NOTICE 与历史 MIT 声明。

## SDK 发布合同

1. 版本是 pyproject.toml 的单一事实来源，维护 uv.lock；tag 必须为对应的 vX.Y.Z
   或 vX.Y.ZrcN，提交必须属于 master。已发布的版本、tag 和资产不覆盖。
2. PR/master CI 使用 Python 3.11–3.14 做静态检查；成功后单一 build job 构建 wheel/sdist，
   检查 metadata，并在无 backend/无 signing extra 的新环境导入 wheel。
3. tag 复用同一门禁与 build job，发布 job 只下载其 artifact，不重新构建。
4. 资产为 opsmesh_plugin_sdk-VERSION-py3-none-any.whl、同版本 tar.gz、SHA256SUMS。
   GitHub provenance attestation 绑定来源仓库/工作流/commit 与资产摘要。
5. rc 标签发布为 prerelease。流水线失败不视为发布成功；已有 release 禁止覆盖。
   发布 job 部分失败后先核查资产与证明，再人工修复，当前不实现自动补传。
6. 仓库尚未配置 PyPI Trusted Publisher，不运行 uv publish/twine upload，也不声称包已上架。
   下游可安装 GitHub Release wheel，或固定完整 commit 的源码归档，不能依赖浮动 master/latest。
7. 不为 SDK 发布 Docker 镜像；它是库。可部署插件自己的镜像遵守架构文档中的插件发布合同。

```sh
pip install ./dist/opsmesh_plugin_sdk-0.1.0-py3-none-any.whl
pip install './dist/opsmesh_plugin_sdk-0.1.0-py3-none-any.whl[signing]'
```

从 OpsMesh 8d9fc408 提取初始 SDK；后续唯一源码 owner 是本仓库。
平台的依赖位置由平台 pyproject.toml/uv.lock 决定，不通过手工复制同步。
跨仓库合同变更先发布/推送 SDK 不可变版本，再更新平台固定依赖并运行现有接入流程。
插件目录与平台拉取设计见 [架构与分发合同](architecture.md)。
