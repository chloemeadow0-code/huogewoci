# Hogwarts MCP 游戏第一版

**已补齐云端部署版**：网页注册凭证、人和 AI 使用独立账号、多人共享校园、HTTP MCP，
Docker / Zeabur 持久卷配置。启动与部署请看 [DEPLOY.md](DEPLOY.md)。
下文的 stdio 命令仍可用于原单玩家本机入口。

基于 `matluz1/lorekit`，上游 commit `db83614862bc2220013a19e42f136a63ba811ea7`。
扩展日期：2026-10-02。仅新增文件，没有改动上游核心、GM 入口或原有规则包。

## 启动

本目录已经有经过测试的 `.venv`。在本目录打开 PowerShell：

```powershell
.\start-hogwarts.ps1 -Mode demo
.\start-hogwarts.ps1 -Mode test
.\start-hogwarts.ps1 -Mode server
```

server 是 **stdio MCP**，供 MCP 客户端拉起，终端等待协议输入是正常现象。
默认持久存档为本目录的 `data/hogwarts.db`，首次启动自动建世界；再次启动继续已有状态。
可用 `-Database 'C:\path\another.db'` 开启另一个独立玩家世界。
Demo 每次使用临时数据库，不覆盖玩家存档；输出 `hogwarts-demo.json`。

换到另一台 Windows 机器时，重新创建虚拟环境，不要搬运 `.venv`：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r systems/hogwarts/requirements.txt
.\.venv\Scripts\python.exe -m pip install pytest pytest-asyncio
```

需要 Python 3.12 或更新版本。**Hogwarts 专用入口已在 Python 3.12.10 实测**。
上游完整 LoreKit 发行包声明 Python >=3.13；本入口从源码调用已兼容的部分，不通过
`pip install -e .` 安装整个上游包，也不加载上游 GM/完整依赖。
`systems/hogwarts/requirements-lock.txt` 记录本次测试的全部依赖版本。

MCP 客户端可使用根目录 `hogwarts.mcp.json` 中的 `mcpServers.hogwarts` 配置。
这是当前机器的绝对路径配置，搬迁后更新 command / args / PYTHONPATH。
只连接这个专用入口；原版 `lorekit.server` 是另一个 GM 服务器。

## 从玩家视角开始

新生：注册时选择学院，一年级、榛木独角兽毛魔杖、体力 100、金币 20、学院分 0。
初始在校医院休息床位睡觉；`sleep(hours=0)` 起床。游戏初始时间为 2026-09-07 周一 06:00。
课程是原创学期安排，教授在不同时段主持三个入门小班。

| 课程 ID | 地点 | 工作日时间 | 学会 |
|---|---|---|---|
| charms | library 图书馆 | 09:00–10:00 | 荧光闪烁、诺克斯、漂浮咒 |
| potions | potions 魔药教室 | 13:00–14:00 | 清理一新、修复如初 |
| herbology | greenhouse 温室 | 15:00–16:00 | 清水如泉 |

必须在开课后 15 分钟内签到，人在课堂地点；同一天不能重复领课程奖励。
其余咒语通过携带练习册在图书馆 `study` 学习。`read(textbook)` 只提供目录。
施法用英文目标 ID，可从 `look` 获取。熟练度与当前体力决定成败，失败施法也消耗体力。
已学魔咒熟练度 1～5，练习增加熟练度；没有学过时，练习与施法都被规则层拒绝。

| 魔咒 ID | 目标 | 实际状态变化 |
|---|---|---|
| lumos / nox | wand | 魔杖照明开 / 关 |
| wingardium_leviosa | feather | 羽毛悬浮 |
| accio | feather | 羽毛移到面前（现场对象，不生成背包副本） |
| alohomora | chest | 图书馆普通练习箱解锁 |
| reparo | cup | 修复杯子 |
| scourgify | cauldron | 清洗坩埚 |
| aguamenti | plant | 浇灌植物 |
| protego | self | 10 分钟护盾，超时移除 |
| expelliarmus | dummy | 练习假人解除武装 |

## 地图和原创人物

```text
图书馆──禁书区（许可）
  │
礼堂──魔药教室
  ├──校医院
  ├──温室──黑湖──魁地奇球场
  └────────黑湖──禁林入口
                 └──霍格莫德入口（校界内摊位）
```

上图概览；权威出口在 `world.json` 和 `look`。10 个地点都有双向明确连接，不允许跨图传送。
地点之间的路程被抽象为 10 分钟，第一版没有走廊、楼梯和公共休息室节点。
霍格莫德节点是**校界内入口与摊位**，没有进入村庄的出口，未成年人不会因此绕过年级限制。
禁林节点只到入口，没有深入森林的出口。禁书区许可通过完成魔咒课后向教授
`ask(npc="professor", topic="permission")` 获得，开锁咒不能绕过。

| NPC ID | 原创人物 | 身份 / 通常地点 |
|---|---|---|
| professor | 艾琳·雾梣 | 教授，图书馆；上课时按课表到对应教室 |
| healer | 赛芙·苔溪 | 校医，校医院 |
| student | 米洛·星棱 | 学生，礼堂 |
| merchant | 塔文·铜枝 | 商人，霍格莫德入口 |
| caretaker | 奥伦·石栎 | 管理员，禁林入口；夜间巡查校园 |

向商人 `ask(topic="buy tonic")` 可用 5 枚金币购买恢复药剂。
NPC 对话、赠礼、课程与违规都会形成 LoreKit NPC 持久记忆，后续问候会识别旧相识。
原创小线索：学习开锁咒 → 解锁图书馆练习箱 → `search(chest)` → 发现温室标签的去向。

## 工具边界和知识

玩家服务器精确注册以下 18 个工具：

`look, move, inspect, talk, ask, give, check_status, check_schedule, check_inventory,
attend_class, study, practice_spell, cast_spell, use_item, read, search, sleep, wait`

没有管理员工具、SQL 工具、GM 状态工具、读取世界真相的资源或提示词接口。
服务器绑定一个玩家数据库，调用不接受角色 ID / 会话 ID，不能通过参数读其他角色。
世界秘密、NPC 私密资料和 NPC 原始记忆在服务器端；输出手动投影公开字段。
`known_facts` 只有对话、阅读和符合条件的搜索才会解锁。输入文字不能直接学习咒语或改数值。
这实现的是 **MCP 接口边界**：本机能直接读源码和 SQLite 的管理员当然可以看到真相。

规则引擎决定物品消耗、金币、课程、权限、施法与违规，AI 客户端负责叙事。
所有成功的行动自动存档。被拒绝的行动恢复完整操作前快照，不耗时、不扣物品、不残留 NPC 记忆。
宵禁为 22:00–06:00；跨过宵禁的长时间等待同样会被抓，记录违规、扣 5 分、送回校医院。
每个夜晚只记一次扣分；重复夜游仍会被送回休息，但不会重复扣分。

## 复用与文件

| 新文件 | 职责 / 原版复用 |
|---|---|
| src/hogwarts/engine.py | 世界初始化、玩家动作；LoreKit SQLite schema、characters、regions、session_meta |
| src/hogwarts/rules.py | 确定性施法、参数约束，独立于 AI 文本 |
| src/hogwarts/server.py | 使用与 LoreKit 相同的 FastMCP SDK，独立实例与 18 工具白名单 |
| src/hogwarts/demo.py | 用真实玩家动作跑完整 Demo |
| src/hogwarts/operator.py | 本机操作者命名存档 / 读档入口，不注册 MCP 工具 |
| systems/hogwarts/*.json | system、world、spells、courses、items 原创数据包 |
| tests/hogwarts/*.py | 游戏规则、知识隔离、NPC 记忆、上游分支恢复、真实 stdio MCP |
| start-hogwarts.ps1 / hogwarts.mcp.json | Windows 启动和当前机器 MCP 客户端配置 |

时间调用 `lorekit.narrative.time`，区域调用 `lorekit.narrative.region`。
NPC 调用 `lorekit.npc.memory.add_memory/get_memories/set_core`。
存档直接调用 `lorekit.support.checkpoint` 的全量 / delta、命名存档和分支恢复。
扩展 JSON 状态放在 `session_meta.hogwarts_state`，因此背包、魔咒、物体状态、知识、关系和违规
都随原版存档一起回滚；NPC 记忆和人物位置也在上游快照范围内。
新 system.json 由校园规则引擎读取，**不是**注册进原版 cruncher 的 D20 system schema。

本机操作者可以在停止玩家服务器后保存、恢复世界：

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
.\.venv\Scripts\python.exe -m hogwarts.operator save first-day
.\.venv\Scripts\python.exe -m hogwarts.operator list
.\.venv\Scripts\python.exe -m hogwarts.operator load first-day
```

读档后继续行动会复用 LoreKit 分支机制；有命名存档的未来路线会得到保留。

## 当前限制

- stdio 入口为单玩家；HTTP 入口支持多凭证共享校园。单进程串行行动，
  不支持多个服务器 / 操作者同时写同一个数据库。
- NPC 使用规则化中文回复与持久记忆，没有接入独立 LLM Agent、自由生成剧情或向量检索。
  无需 API key；不下载 sentence-transformers 模型。未来可在公开回复边界内加叙事层。
- 学院可选择；年级和魔杖固定，没有升学、完整战斗 / 魁地奇 / 魔药配方。
- 教室时段简化、课表每周重复，休息只在校医院，护盾目前是持久效果而非完整战斗系统。
- HTTP 入口已经有网络凭证认证、网页前端与 HTTP MCP；仍不是商业发布版。
- 验证针对 Hogwarts 扩展与实际复用路径，不宣称运行了上游全部 TTRPG 测试。
- 上游测试发现器会提示此包没有 D20 `test_config.json`；本包使用独立的校园规则测试，
  不伪造 D20 配置来消除提示。

## 本次验证

2026-10-02，Python 3.12.10 / MCP SDK 1.30.0：**35 个测试全部通过**。
两个提示来自上游 D20 配置检测与 Starlette 的 httpx 测试适配器；无失败或跳过。
本机报告保存在开发工作区，远端结果见仓库 Actions。

验证了所有十种魔咒的实际效果、未学习禁用、施法失败消耗、目标校验、地点连接、
三个课程、签到窗口、禁书区许可、交易与物品守恒、世界知识隔离、NPC 私密字段不泄漏、
NPC 记忆重用、重启恢复、原版命名存档及分支恢复、长时间等待宵禁与重复巡查。
测试还启动真实 stdio MCP 子进程，完成握手、确认恰好 18 个工具、拒绝管理员工具，
并通过客户端重放整条 Demo，逐步比对玩家返回结果。

Demo 最终：学会荧光闪烁等三个课堂魔咒，课程奖励 +2 学院分，夜游扣 5 分，
学院分为 -3，记录奥伦·石栎的巡查见证并送回校医院。`hogwarts-demo.json` 保存完整过程。
启动脚本的 Demo 模式也已实际运行；原版已跟踪文件的 diff 为空。

## 许可

原始代码许可为 Apache-2.0，保留仓库原 LICENSE 及已有归属说明；新增代码也按 Apache-2.0 提供。
没有引入 pf2e/mm3e 规则内容。本扩展是非官方同人原型，NPC 和线索均原创；
LoreKit 的代码许可不授予 Harry Potter / Hogwarts 世界观、名称或商标的权利。
商业发布前需要另行确认这些权利。

### 学院选择

注册页面可选四大学院。旧账号此前被默认分到拉文克劳，可通过现有玩家工具一次性确认学院：`use_item(item="admission:Hufflepuff")`。原有进度保留，确认后不能重复分院。AI 可先用 `check_status` 查看提示。
