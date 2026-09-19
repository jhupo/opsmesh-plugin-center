# 插件中心、SDK 与平台边界

状态：2026-09-19。采用 sdk/ 与 plugins/<name>/ 单仓库结构。

SDK 维护公共合同、签名和客户端。每个插件独立声明渠道依赖、版本及部署方式。
新贡献通过 plugins/<name> 合入；无需复制 SDK 或为每个插件建立 Git 仓库。
SDK 不导入插件；插件不互相导入，只调用 SDK 公共接口。根 uv workspace 统一开发锁文件，
发布分别构建 wheel/sdist，SDK wheel 不包含任何渠道实现或渠道依赖。

插件目录包含 plugin.json、pyproject.toml、README、LICENSE、src 和 tests。
有卡片时增加 card-templates/<用途>/<版本>，有部署需求时增加 deploy，不创建空目录。
card.json 是厂商 UI，mapping.json 是 SDK CardTemplate，preview.json 是无敏感样例。
模板随插件分发包交付。安装配置仍需引用实际发布的 template_id。

平台拥有受控 HTTPS 目录→不可变描述文件→验签→权限/配置预览→管理员绑定→安装。
源码 PR 合并不自动给工作区安装、信任或授权。可安装目录采用 PluginCatalog，记录
release_url、准确 SHA256、发布者和版本；没有签名发布就不能生成可安装条目。

SignedPluginRelease 的 descriptor v2 绑定 manifest、平台/SDK 范围、许可证、仓库、完整提交
和可选的固定摘要容器镜像。SDK 0.4 直接采用 v2，不加入旧描述合同兼容分支。
同 key/version 不覆盖。下载不会 pip install 或执行第三方代码。
插件独立部署，通过安装凭据使用平台服务，再按 sender 绑定检查真实用户权限。
无重启配置更新不代表 Python 热加载。OpsMesh 已接入隔离进程的持久部署控制；管理员另行
批准 digest-pinned 运行模板，下载目录不会自动执行代码。真实容器/钉钉验收及 Web 界面仍未完成。

服务合同见 [services](services.md)，贡献和发布见 [development](development.md)。
