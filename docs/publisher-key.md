# 发布者验证公钥

状态：2026-09-20。发布者 key ID：`opsmesh-plugins`。

算法：Ed25519，以下为原始 32 字节公钥的 Base64：

```text
EYVrq8LSPqlL7jH2/o1oT6UDBtLnrxP2qcjkn6rmSto=
```

私钥仅保存在本仓库 Actions Secret `OPSMESH_PLUGIN_SIGNING_KEY`。
公钥发布不自动建立工作区信任；管理员核对发布者后显式添加信任。
私钥轮换须使用新的 key ID 并保留已有不可变发布的验证资料。
