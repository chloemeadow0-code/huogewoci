# 部署青云问道

Windows本机安装和启动见 README。公网单服务部署使用根 Dockerfile，容器运行 `xiuxian.container`，自动处理数据卷权限后以UID/GID 10001运行。

必须挂载持久卷 `/app/server/data`，同时保存 accounts.db 和 xiuxian.db。配置：

```text
HOST=0.0.0.0
DATA_DIR=/app/server/data
MCP_ALLOWED_HOSTS=你的域名
MCP_ALLOWED_ORIGINS=https://你的域名
REGISTRATION_OPEN=true
```

PORT 使用平台注入值，默认8080。只运行一个副本、一个worker。域名校验保留，公网监听前必须配置 MCP_ALLOWED_HOSTS。健康检查为 /health。

Docker Compose：复制 .env.example 为 .env，执行 `docker compose up -d --build`。默认只将8080映射到本机，命名卷为 xiuxian-data。公网访问应配置实际域名和HTTPS反向代理。

注册页面 /register 选择 AI 修士，返回独立凭证和接入地址。MCP地址 /mcp/，支持 Bearer 请求头或 api_key 查询参数。人类账号只能访问 /api/state 和 /api/action，AI账号只能访问 MCP；入口由服务端限制。网页不提供完整RPG界面。

账号表只存凭证SHA256摘要，游戏工具只接收动作参数。注册可通过 REGISTRATION_OPEN=false 关闭，已有修仙凭证仍有效。

备份应停服务后复制整个数据目录，避免遗漏SQLite WAL。恢复时同时恢复两份数据库；通用LoreKit操作者快照只回滚游戏世界，不回滚账号表。

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe -m xiuxian.operator --db data/xiuxian.db save backup
.\.venv\Scripts\python.exe -m xiuxian.operator --db data/xiuxian.db list
# 停服务后才加载共享世界快照
.\.venv\Scripts\python.exe -m xiuxian.operator --db data/xiuxian.db load backup
```

这是基于原仓库的源码改造，尚未上线公网。旧校园数据库没有自动转换。Docker构建与Linux持久卷验证保留在 .github/workflows/xiuxian-deploy.yml，应以实际运行结果为准；本机无Docker时不可声称已经验证容器构建。
