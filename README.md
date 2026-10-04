# 灵汐岛 · AI 与人类共游的修仙 MCP 游戏

在本仓库现有“青云问道”上继续改造，现统一名为灵汐岛。账号、凭证、出生属性、修行进度与旧委托保留；首次打开新版服务自动迁移至独立 SQLite 表。沿用现有战斗、宗门路线与部署入口，吸收 allotment-relay 的聚合命令、事务幂等、阶段任务、灾档和模块化地图设计。

AI 选择行动、招式和策略；命中、伤害、控制、掉落、突破、炼制和任务条件由固定数据及代码结算。随机序列持久化，数值不接受自由文本覆盖。

## 启动

Windows PowerShell，在仓库目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r systems/xiuxian/requirements-deploy.txt
$env:REGISTRATION_OPEN='true'
.\.venv\Scripts\python.exe run-xiuxian.py
```

Linux：

```sh
python -m venv .venv
.venv/bin/python -m pip install -r systems/xiuxian/requirements-deploy.txt
REGISTRATION_OPEN=true .venv/bin/python run-xiuxian.py
```

打开 `http://127.0.0.1:8080/`。创建角色时灵根及资质独立随机生成，之后固定；道号可以修改。新角色选择四宗或散修，路线确认一次。保存注册时返回的凭证；服务端只保存摘要。已有角色直接使用原凭证。

## AI 和网页共号

网页“AI 修士接入”展示当前角色的凭证和配置。AI 与网页使用**同一凭证**，两端都能行动，网页每 5 秒刷新状态。注册时的 human/ai 仅为历史标签，不再划分接口权限。不同凭证仍隔离角色；玩家无法访问管理员快照或指定别人的身份。

Streamable HTTP 接入（客户端字段可能不同）：

```json
{"mcpServers":{"lingxi":{"type":"http","url":"http://127.0.0.1:8080/mcp/","headers":{"Authorization":"Bearer xx_sk_替换为自己的凭证"}}}}
```

兼容 `api_key` 查询参数；网页生成配置使用请求头。本地 stdio：

```json
{"mcpServers":{"lingxi":{"command":"C:/项目/.venv/Scripts/python.exe","args":["-m","xiuxian.server","--db","C:/项目/data/xiuxian.db"],"env":{"PYTHONPATH":"C:/项目/src"}}}}
```

stdio 使用本地独立角色 `local`；共用线上角色请使用 HTTP 凭证。MCP 只注册 13 个聚合工具，完整子命令放入 `command`，例如：

```json
{"name":"cultivate_ops","arguments":{"command":"meditate 4","request_id":"修士一-操作001"}}
```

先调用 `relay_manual`，各工具支持 `help`，空命令返回本类默认状态。相同 `request_id` 和参数的重试返回原结果；不同操作不可复用编号。每次返回 `ok/result` 或错误、`changes`、`new_events`、`available_actions`。

## 当前可玩

22 个地点、十二宗与散修、26 个正常 NPC、14 类敌对人物、46 条阶段任务、11 类世界事件、10 类持久灾档、独立灵兽（灵醒/化形两阶进化）、炼丹炼器、宗门贡献殿、商店黑市及托管拍卖、秘境潮汐宝藏。境界为炼气/筑基/金丹/元婴，每境四阶段；秘境筑基后每七个游戏日的前两日开放，每角色每周期进入一次。

循环：选路 → 修炼 → 请教导师 → 接委托 → 青竹林探索与逐回合斗法 → 获得材料 → 回宗门逐阶段交付 → 灵石/声望/贡献 → 买丹药与学习功法 → 筑基 → 月汐湖、遗址和潮生秘境。

详细命令、全部内容、数据库、公式和待完善内容见 [LINGXI.md](LINGXI.md)，架构与修改文件见 [IMPLEMENTATION.md](IMPLEMENTATION.md)，Zeabur 和存档维护见 [DEPLOY.md](DEPLOY.md)。网页 `/manual` 提供人类操作说明。

## 验证

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe -m pytest tests/xiuxian -q
.\.venv\Scripts\python.exe -m xiuxian.island_demo --output lingxi-demo.json
```

完整循环演示只使用玩家聚合命令，不授予额外资源。测试包括真实 stdio/HTTP MCP、保存恢复、并发幂等、AI/Web 共号及旧存档迁移。容器构建和持久卷重启由 GitHub 工作流检查。世界按玩家行动推进游戏时间；第一版没有现实时间后台调度、组队或完整宗门政治。
