# 部署灵汐岛

沿用原青云问道服务、GitHub 仓库和数据卷。推送代码与 Zeabur 服务部署是两件事：应在服务发布日志和线上 `/health` 确认当前版本。无需创建新账号或清空数据。

## Zeabur

连接本仓库 `main`，构建目录为仓库根目录，使用根 `Dockerfile`。入口 `python -m xiuxian.container`，处理卷权限后以 UID/GID 10001 运行。必须保留持久卷 `/app/server/data`，同时保存 `accounts.db` 和 `xiuxian.db`。

```text
HOST=0.0.0.0
DATA_DIR=/app/server/data
MCP_ALLOWED_HOSTS=实际服务域名
MCP_ALLOWED_ORIGINS=https://实际服务域名
REGISTRATION_OPEN=true
```

PORT 使用平台注入值，默认 8080；只运行一个副本、一个 worker。配置实际域名和 HTTPS。检查 `/health` 应返回 `version: lingxi-v1`、`tools: 13`。随后重连 MCP 让客户端刷新工具列表。若仍显示旧工具，检查发布是否使用最新提交、是否完成重建，以及 MCP 是否连接同一域名。

`/mcp/` 是 Streamable HTTP；`Authorization: Bearer xx_sk_...`。同一凭证可登录网页并操作同一修士，无 human/ai 权限拆分。`/api/v1/state`、`/api/v1/me`、`/api/v1/command`、`/api/v1/rename` 为新版接口，旧 `/api/state`、`/api/action`、`/api/rename` 保留兼容。

修改请求通过 `request_id` 或 `Idempotency-Key` 重试。命令格式：`{"tool":"travel_ops","command":"go 青竹林","request_id":"唯一编号"}`。注册 `/api/register`；注册关闭不影响已有凭证。

## 迁移与备份

发布前停服务，复制**整个**数据目录作为备份。首次新版服务打开旧数据库，自动将青云问道 `session_meta.xiuxian_state` 导入独立表，并将旧 `accounts` 表导入 `api_keys`；凭证摘要不变。旧 JSON 仅保留为恢复来源，新服务不再写它。旧校园 Hogwarts 存档不在此次迁移范围。

不要同时运行旧服务和新版服务，旧程序只看到迁移前的 JSON。回退旧程序时必须恢复发布前备份；不能直接读取新版进度。迁移后的首次运行要观察启动日志和角色状态。

本地管理员快照涵盖独立游戏表、拍卖、历史及幂等缓存；不包括另一个数据库中的账号。快照存为备份 JSON，实时状态仍使用独立表。加载前必须停游戏服务：

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe -m xiuxian.operator --db data/xiuxian.db save backup
.\.venv\Scripts\python.exe -m xiuxian.operator --db data/xiuxian.db list
# 先停服务；加载回滚整个共享世界
.\.venv\Scripts\python.exe -m xiuxian.operator --db data/xiuxian.db load backup
```

完整恢复同时恢复 `accounts.db` 与 `xiuxian.db`，停机复制整个目录以涵盖 SQLite WAL。管理员快照不暴露给 AI 玩家。

Docker Compose 保留原入口：复制 `.env.example` 为 `.env`，配置域名，`docker compose up -d --build`。默认端口只映射本机。CI 工作流 `Lingxi deploy checks` 执行 Python 测试、Docker 构建、真实容器注册及挂载卷重启验证；应以实际工作流结果为准。

## 随机数密钥（rng_key）的保管

随机判定由服务端密钥参与生成：密钥存在 `xiuxian.db` 的 `world_state.rng_key`，管理员快照又把整份状态（含该列）存在同一库的 `snapshots` 表里。因此：

- 默认 `operator save` 生成的快照**包含密钥**，拿到快照文件的人可以复算后续所有随机判定。快照文件要按机密保管，不要发给任何未被授权的人。
- 需要分享快照时用 `--redact-key`（仅 save 可用）：快照里的 `rng_key` 置为 NULL，密钥不出现在快照正文。取舍：用脱敏快照 `load` 后，世界会自动生成新密钥并继续运行，但**原随机序列不可复现**（历史记录里的旧点数仍可读，只是无法用它推算或重放后续判定）。
- 无论是否脱敏，`xiuxian.db` 本体（含 WAL/SHM）始终包含密钥：整库备份、打包目录、挂载卷镜像都等同于交出密钥，分享前需自行脱敏或只交付 `--redact-key` 快照。
- 相关背景见 LINGXI.md"奖励与防刷规则"一节的"随机点由持久化计数器加服务端密钥 world_state.rng_key 的 HMAC 产生"。
