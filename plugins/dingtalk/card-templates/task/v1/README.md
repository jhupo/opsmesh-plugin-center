# 任务卡片 v1

状态：2026-09-19，结构核对完成；钉钉设计器导入/发布与真机交互待验收。

- card.json：钉钉标准卡片设计器格式，editorData 包含组件树、变量和按钮回调。
- mapping.json：OpsMesh CardTemplate，映射流式文本、状态及事件标识，不是 UI 模板。
- preview.json：无真实用户数据的预览变量。

在钉钉卡片平台创建标准卡片，通过“更多→导入”导入 card.json，预览并保存/发布。
widgetInfo 留空，由设计器根据 editorData 编译；本仓库不重写钉钉模板编译器。
发布后把实际 template_id 填入 mapping.json 的部署副本，并写入安装配置的 card 字段。
严禁把示例 template_id 当成可用模板。无法导入或预览失败时不要发布。

title 显示任务标题，status 显示状态，markdown 接收覆盖式流式预览和最终结果。
三个按钮以 request 回调携带 params.action=pause/resume/cancel，不携带用户或权限声明。
服务端仍按卡片、原发送人和实时权限检查；客户端按钮可见性不是安全边界。
UI 与映射变更一起升模板目录版本；旧投递保留原模板快照。

格式参考钉钉官方导出示例（独立编写组件内容，不复制厂商模板编译结果）：
https://github.com/open-dingtalk/dingtalk-card-examples/tree/main/examples/helloworld
