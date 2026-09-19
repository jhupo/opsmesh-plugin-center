# 贡献与发布

状态：2026-09-19；本次不创建正式 tag，不宣称已在 PyPI 发布。

新增插件在 plugins/<name> 创建独立 pyproject、plugin.json、release.toml、LICENSE、README、src 和
产品流程测试；配置、卡片和部署资料都放在该插件目录。不得将厂商依赖加入 sdk。
名称采用小写短横线，Python 包采用下划线。SDK 包名仍为 opsmesh-plugin-sdk。

根目录执行 `uv sync --all-packages --all-extras --all-groups`，锁文件仅根 uv.lock 一份。
`uv run --package opsmesh-plugin-sdk ruff check sdk/src` 做 SDK 静态检查；插件同理。
`uv build --package opsmesh-plugin-sdk`、`uv build --package opsmesh-plugin-dingtalk`
分别构建，两种 wheel 不互相打包源码。生产通过发布 wheel 安装，不能依赖开发环境路径。

发布 tag 约定 SDK 为 sdk/vX.Y.Z，插件为 plugins/<目录名>/vX.Y.Z；版本必须匹配该包
pyproject，插件还必须匹配 plugin.json。提交必须属于 master。不能覆盖 tag 或 release。
根 CI 按包验证并各自上传产物；发布下载相同产物，计算摘要并附 provenance。
各插件的 release.toml 声明 publisher_key_id、platform_requires、sdk_requires，许可证取自身
pyproject；流水线不得对所有插件套用一组写死的值。CI 静态检查版本、范围、模板变量及按钮映射，
这不证明钉钉设计器导入、发布或真实回调可用。
插件描述文件使用 SDK 签名能力，私钥只用于发布任务，PR 无写权限或密钥。
SDK 不发布 Docker 镜像，插件部署文件留在 deploy，运营者自行构建部署。

平台只下载经审核的签名 JSON 和目录，不加载源码仓库。目录须指向固定无鉴权 HTTPS
地址、无 query，填写实际字节 SHA256；GitHub 带签名 query 的下载跳转不可直接当平台源。
保持发布描述文件与可执行 wheel 的用途分离。

包名、目录名和插件 manifest.key 是三个不同标识；更改目录不能偷偷变更安装身份。
迁移仓库时先推送 SDK 完整提交，再将 OpsMesh 依赖改为该归档加 #subdirectory=sdk，
更新 uv.lock 并验证安装。远程重命名或推送未完成前，不填写不存在的依赖地址。
