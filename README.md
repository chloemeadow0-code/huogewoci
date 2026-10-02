# 雾梣学期 · 霍格沃茨 MCP 游戏

可部署的原创霍格沃茨校园生活游戏。网页领取凭证，人和 AI 使用独立学生账号；
多人共享校园、物体和叙事时钟，背包、魔咒、课程及已知事实各自独立。

基于 [LoreKit](https://github.com/matluz1/lorekit)，保留其 SQLite 状态、区域 / 时间、
NPC 记忆和分支存档机制，新增独立 Hogwarts 游戏模块。
参考 [潮汐岛](https://github.com/sue1231511/allotment-relay) 的部署与凭证接入结构。
NPC 与剧情全部原创，非官方同人原型。

## Zeabur 部署

1. 新建服务，选择本仓库 `chloemeadow0-code/huogewoci`，分支 `main`。
2. Root Directory 使用仓库根目录，不填写子目录。平台自动读取根 `Dockerfile`。
3. 创建持久卷，挂载到 **`/app/server/data`**。
4. 生成域名后设置以下环境变量，把示例域名换成自己的域名：

```dotenv
HOST=0.0.0.0
DATA_DIR=/app/server/data
MCP_ALLOWED_HOSTS=my-hogwarts.zeabur.app
MCP_ALLOWED_ORIGINS=https://my-hogwarts.zeabur.app
REGISTRATION_OPEN=true
```

`PORT` 使用平台提供的值，未提供时默认 8080。保持一个服务副本。
重新部署后，访问 `/health` 应返回 `status: ok`。打开 `/register` 领取学生凭证，
进入 `/play`。点「创建 AI 学生」，领取另一份 AI 专用凭证并复制接入地址：

```text
https://你的域名/mcp/?api_key=hw_sk_AI专用凭证
```

MCP 类型选择 **Streamable HTTP**，支持 Bearer 请求头认证。
更多步骤、Docker Compose 和备份说明见 [DEPLOY.md](DEPLOY.md)。

## 已实现

- 玩家学院、年级、魔杖、体力、金币、学院分、已学魔咒、背包和已知事实。
- 10 个真正相连的地点、5 个原创 NPC、10 个魔咒、3 门课程及工作日课表。
- 原版 NPC 持久记忆，课程 / 施法 / 物品 / 权限由确定性规则计算。
- 未学魔咒禁止施放，世界秘密按交谈、阅读和搜索逐步解锁。
- 宵禁会记录违规、扣分和送回休息；共用时钟会巡查所有在外学生。
- 玩家 MCP 只开放 18 个指定工具，没有管理员修改工具。

玩法见 [校园说明](HOGWARTS.md)；部署后人类手册在 `/manual`。

## 本机启动与验证

```bash
python -m venv .venv
# Linux
.venv/bin/python -m pip install -r systems/hogwarts/requirements-deploy.txt
REGISTRATION_OPEN=true .venv/bin/python run-hogwarts.py
```

Windows 使用 `.venv\Scripts\python.exe` 安装依赖，并运行 `run-hogwarts.py`；
在 PowerShell 先设置 `$env:REGISTRATION_OPEN='true'`。
默认地址 `http://127.0.0.1:8080/`，默认持久数据目录 `data/`。

```bash
python -m pip install pytest pytest-asyncio
PYTHONPATH=src python -m pytest tests/hogwarts -q
PYTHONPATH=src python -m hogwarts.demo
```

本次 Windows / Python 3.12.10 实测 **34 项测试通过**，含真实 stdio / HTTP MCP、
凭证隔离、并发、重启恢复及完整 Demo；网页端到端与手机布局也实测通过。
GitHub Actions 提供 Linux 测试、Docker 构建和持久卷重启验证，以实际工作流结果为准。

当前限制：单进程、行动推进的全服叙事时钟；NPC 是固定回复结合持久记忆；
初始学院 / 年级 / 魔杖固定。没有完整战斗、跨玩家交易或独立 LLM NPC。

## 许可

保留 LoreKit 的 [Apache-2.0 LICENSE](LICENSE) 和 [NOTICE](NOTICE)。
上游 commit：`db83614862bc2220013a19e42f136a63ba811ea7`。
新增模块也按 Apache-2.0 提供，代码许可不授予 Harry Potter / Hogwarts 的世界观或商标权利。
