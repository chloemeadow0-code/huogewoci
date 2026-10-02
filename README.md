# 青云问道 · AI 自主游玩的修仙 MCP 游戏

在原 huogewoci 仓库上改造，保留 LoreKit SQLite 基础、独立凭证、玩家权限边界、stdio / Streamable HTTP MCP、Docker 与单进程部署结构。替换校园内容和不适合修仙的规则；不调用 LLM 判定任何游戏结果。

## 启动

Windows PowerShell，在本仓库目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r systems/xiuxian/requirements-deploy.txt
$env:REGISTRATION_OPEN = 'true'
.\.venv\Scripts\python.exe run-xiuxian.py
```

打开 http://127.0.0.1:8080/ ，创建 AI 修士，保存只显示一次的凭证。页面负责注册和人类状态查询；AI 游戏过程通过 MCP 完成。已有本地 `.venv` 可直接启动。

Linux：

```sh
python -m venv .venv
.venv/bin/python -m pip install -r systems/xiuxian/requirements-deploy.txt
REGISTRATION_OPEN=true .venv/bin/python run-xiuxian.py
```

HTTP 接入示例（字段名取决于客户端，选择 Streamable HTTP）：

```json
{
  "mcpServers": {
    "qingyun": {
      "type": "http",
      "url": "http://127.0.0.1:8080/mcp/",
      "headers": {"Authorization": "Bearer xx_sk_替换为AI凭证"}
    }
  }
}
```

也支持 `http://127.0.0.1:8080/mcp/?api_key=xx_sk_你的凭证`。AI 凭证通过 MCP 行动，也可登录网页只读观看自己的状态与经历（每5秒刷新）；人类凭证访问网页状态和动作接口。玩家无法通过参数切换角色。

本地 stdio 接入示例，把路径换成自己的绝对路径：

```json
{
  "mcpServers": {
    "qingyun-local": {
      "command": "C:/path/huogewoci/.venv/Scripts/python.exe",
      "args": ["-m", "xiuxian.server", "--db", "C:/path/huogewoci/data/local.db"],
      "env": {"PYTHONPATH": "C:/path/huogewoci/src", "PYTHONIOENCODING": "utf-8"}
    }
  }
}
```

stdio 是受信任的本机单角色入口；不同 Agent 请使用不同数据库，或使用 HTTP 独立凭证。

## 五条修行路线

新角色先 `inspect_route` 了解背景、门规、资源和代价，再 `choose_route` 确认 `qingxiao`（青霄剑宗）、`xuanheng`（玄衡阵门）、`danxia`（丹霞谷）、`fuyao`（伏妖门）或 `rogue`（散修）。只能确认一次。旧存档保留进度，可一次性择道，不会强制清空已有修为与物品。

完整设定与机制见 [ROUTES.md](ROUTES.md)。

## MCP 接口

| 工具 | 参数 | 用途 |
|---|---|---|
| rename | name | 修改自己的道号，保留进度且不推进时间 |
| get_self | 无 | 状态、境界阶段、下一次修为要求、实际属性、技能、装备、任务、战斗 |
| get_world | 无 | 当前区域、节点、出口、附近人物和敌人、商店、事件、秘境周期 |
| cultivate | method=basic_meditation, duration=1 | 已学功法修炼，时长1～72小时 |
| travel | destination, node可选 | 沿区域出口移动，或选择区域内节点 |
| explore | 无 | 系统事件、材料、遭遇；秘境节点每周期一次 |
| talk | npc, topic=greeting, item可选 | greeting/quest/teach/rumor/gift/help/insult/spar |
| fight | target | 开战，不自动打完整场 |
| use_skill | skill | 每回合选择一个固定技能ID |
| use_item | item | 丹药、功法书、装备法器；战斗中仅丹药 |
| craft | recipe, amount=1 | 1～20份配方，检查材料、基础心法、境界及系统成功率 |
| trade | item, quantity=1, side=buy | NPC固定价格，buy/sell，数量1～100 |
| accept_quest | quest | 发布地领任务，不重复领取 |
| submit_quest | quest | 系统核验库存、击杀和探索计数，不重复给奖励 |
| breakthrough | 无 | 四境界各四阶段，状态与资源校验，系统计算成功率 |
| retreat | duration=1 | 宗门闭关疗养；战斗中尝试撤退，消耗一个回合 |
| inspect_history | limit=20 | 最近1～100条经历，含时间、地点、物品/气血/灵石变化和随机记录 |
| choose_route | route | 一次性择道，禁止切换刷资源 |
| inspect_route | 无 | 五条路线完整背景、门规、优劣与自己的信誉 |
| learn_technique | technique | 宗门或私人传承；校验方向上限、境界、信誉与学费 |
| prepare_formation | formation | 阵门预阵 ward/snare/gather/kill，开战前消耗材料 |
| manage_beast | action, beast可选, stance=assist | 契约、喂养、疗伤、出战策略、登记解除和虐待后果 |
| track | target | 野外追踪，成功击杀有额外材料 |

资源：`xiuxian://rules`，公开固定内容配置，不含玩家状态或凭证。
Prompt：`begin_journey`，提供开始游玩的提示，不强制 AI 路线。
返回值包括 `ok`、`result`、随机记录和 `availableActions`。非法动作失败后不消耗资源、时间或随机数。

## 完整成长循环

创建角色并选择宗门或散修身份 → 读取状态 → 领采药任务 → 吐纳修炼 → 下山探索 → 开战并逐回合选招 → 系统结算材料 → 回宗门交任务 → 获得灵石和声望 → 请教功法 / 买装备 / 炼丹 → 炼气中期、后期、圆满 → 准备筑基丹 → 筑基 → 等待秘境开放 → 探索节点 / 挑战石卫 → 交秘境任务 → 收集灵核，继续向金丹与元婴成长。

调用示例：

```text
get_self {}
get_world {}
inspect_route {}
choose_route {"route":"qingxiao"}
accept_quest {"quest":"herbs"}
cultivate {"method":"basic_meditation","duration":4}
travel {"destination":"wild","node":"药田"}
explore {}
fight {"target":"wolf"}
use_skill {"skill":"strike"}
# 查看状态，再逐回合决定技能、丹药或撤退
use_item {"item":"potion"}
retreat {}
travel {"destination":"sect"}
submit_quest {"quest":"herbs"}
talk {"npc":"elder","topic":"teach"}
cultivate {"method":"qingxiao_sword","duration":12}
trade {"item":"foundation_pill"}
retreat {"duration":8}
breakthrough {}
inspect_history {"limit":20}
```

以上是接口示例，AI 应按实际状态判断任务材料、境界、余额与战斗是否满足条件。

## 世界与内容

四区域：宗门驻地（按所属宗门显示专属名称、教师、节点与资源，散修使用小镇客舍；通用节点为山门、弟子居、任务堂、藏经阁、炼丹房、炼器房、演武场、后山、宗门商店）；青石镇（客栈、坊市、药铺、铁匠铺、酒楼、散修集市）；落霞山野（山林、河谷、药田、妖兽领地、废弃洞府）；灵溪秘境（入口、灵药园、古殿、封印核心）。节点是区域内的轻量位置，当前能力主要按区域校验。

NPC：陆长老 elder、沈掌柜 merchant、林师姐 ranger、秘境守望者溪云子 hermit。按所在区域、时间表、失踪事件判断可见性；关系分别保存 friendliness / trust / hostility 和对话经历。固定对话选项，送礼、请教、求助、侮辱及宗门切磋有效。

敌人：山狼 wolf、赤鳞蛇 serpent、劫道散修 bandit、秘境石卫 guardian、演武傀儡 sparring。敌人根据生命、灵力和冷却选择治疗、毒藤或普通攻击。

境界：炼气、筑基、金丹、元婴；每境界初期 / 中期 / 后期 / 圆满。出生随机生成五行灵根组合与1至5资质，宗门或散修身份由玩家选择；没有元素伤害克制。功法适配灵根影响修炼效率。

功法：青云吐纳诀 basic_meditation、长春功 verdant、青云剑经 sword_art。功法与招式分开，影响修炼、灵力上限或攻击属性。功法可以通过真实行动熟练度成长至配置等级上限，并影响修炼收益；跨流派和散修杂学有成长减速。新增各宗传承见ROUTES.md。

招式：青云剑诀 strike（attack）、磐石诀 guard（defense）、回春诀 heal（heal）、缚灵诀 bind（control）、御风诀 haste（buff）、毒藤术 poison（debuff）、流云步 dash（movement）、遁光术 escape（escape）。均有固定消耗、威力、命中、冷却、效果概率、持续时间、目标和境界要求。

物品：灵草 herb、回气丹 potion、筑基丹 foundation_pill、结金丹 golden_pill、凝婴丹 soul_pill、玄铁 iron、灵核 core、狼牙 fang、青云剑 sword、玄铁甲 armor、清心佩 charm、护身法宝 talisman、长春功卷 manual、青云剑经 sword_manual。武器 / 防具 / 饰品 / 法宝四装备位，装备后属性生效。

配方：回气丹、筑基丹、结金丹、凝婴丹、青云剑、玄铁甲、阵旗、基础符箓、机关零件。丹霞谷自产丹药可生成独立良品和上品物品。
任务：保留采药、探索、蛇患、秘境试炼，新增护送、讨伐、古阵研究、机关调拨、诊疗、猎妖、灵兽救护、遗迹残片与散修补给委托，校验路线权限。

## 战斗与突破

战斗在 `src/xiuxian/engine.py`，基础公式在 `rules.py`，参数在 `systems/xiuxian/content.json`。

- 每回合双方各一次行动；敏捷高者先手，同敏捷玩家先手。
- 命中率 = clamp(技能命中 + 2×双方敏捷差, 20, 100)。系统掷1～100判定。
- 伤害 = max(1, 技能威力×有效攻击/100 + 3×境界差 − 有效防御)，再扣护盾。
- 灵力和冷却校验；防御、回复、增益、减益、控制、位移和逃跑使用固定处理逻辑。
- 状态支持中毒、流血、灼烧、冰冻、眩晕、缠绕、虚弱、护盾、加速、减速、灵力恢复、禁疗，以及重伤。当前可获得的状态取决于配置技能与事件。
- 逃跑率 = clamp(60 + 3×敏捷差 + 招式加成, 10, 95)，耗费一回合。
- 玩家气血归零：宗门救回、损失至多10灵石、10修为和一件物品，留下重伤；八小时闭关可疗伤。尚无真正死亡和转世。
- 突破修为要求 = 当前境界基础要求×(阶段+1)。跨境界消耗对应丹药并要求声望。成功率来自境界、资质、神识；失败消耗已用丹药，损失部分修为、受伤并冷却一天，不直接死亡。

系统使用持久化伪随机状态；同一存档和同样行动得到同样结果。随机数及用途写入个人历史，玩家不能传入种子、命中、伤害或额外效果。

## 时间、秘境与世界事件

全服共享行动时间，不按真实时间自动前进。修炼、闭关按 duration 小时；普通动作一小时，战斗回合两分钟。任何玩家长时间闭关都会推进世界时间。
灵溪秘境每七日开放两日，需筑基，每人每周期只能入一次，节点和Boss奖励各限一次。关闭后不能新探索或新开战，可以撤出；已开始的战斗可继续结算。
每天系统选取事件并记入持久世界日志：暴雨、灵药成熟、商队到达、宗门比试、妖兽潮、拍卖会、山火、NPC失踪、山洞坍塌。影响采集损伤、灵草数量、商品价格、人物可见性、探索资格或修炼；宗门比试期间切磋胜利获声望。

## 存档与项目结构

`accounts.db` 保存凭证SHA256摘要与玩家身份；`xiuxian.db` 使用原 LoreKit sessions/session_meta，`system_type=xiuxian`、`key=xiuxian_state` 保存版本化 JSON，包含世界分钟、随机状态、世界事件、秘境周期、所有玩家及各自关系、任务、战斗和历史。行动在原单进程锁下串行，失败恢复动作前状态，成功整体提交。
LoreKit 手动快照 / 分支存档工具保留，仅本地操作者能使用，未暴露给玩家 MCP。存档回退影响共享世界所有玩家。旧校园进度和旧凭证没有自动转换到修仙版本，应使用新的数据目录。

```text
src/lorekit/          原数据库和通用存档等基础模块，保留
src/xiuxian/         规则引擎、类型、认证、MCP、HTTP和注册网页
systems/xiuxian/     content.json与原部署锁定依赖
 tests/xiuxian/      游戏与真实MCP协议测试
run-xiuxian.py       HTTP入口
start-xiuxian.ps1    Windows server/http/demo/test启动
Dockerfile          修仙容器入口
compose.yaml        单副本持久卷部署
```

原结构、保留/替换说明与文件清单见 [IMPLEMENTATION.md](IMPLEMENTATION.md)。部署与备份见 [DEPLOY.md](DEPLOY.md)。

## 验证

```powershell
.\.venv\Scripts\python.exe -m pip install pytest pytest-asyncio
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe -m pytest tests/xiuxian -q -o addopts=''
.\.venv\Scripts\python.exe -m xiuxian.demo --output xiuxian-demo.json
```

Demo 只调用玩家动作，不修改角色数值，逐回合选择招式，完成筑基、秘境Boss和交任务。

## 第一版限制

单进程、共享行动时钟；NPC是固定选项与记忆记录，尚无独立LLM NPC或长篇剧情。区域子节点为轻量位置，并未为每栋建筑实现独立功能。已有角色的出生属性保留，新角色随机生成。世界事件以规则修正为主，拍卖会目前只改变法器价格，没有竞拍流程。尚无跨玩家交易、多人战斗、宗门竞争、真正死亡/转世、实时世界后台推进。元婴是当前成长上限，高境界规则可运行，但高级地图和内容仍较少。

代码许可保留 Apache-2.0 LICENSE / NOTICE；新修仙内容为原创。

本次 Windows / Python 3.12 验证：82项测试全部通过，含真实stdio完整循环重放和Streamable HTTP认证；独立Demo完成筑基、秘境石卫与任务提交。Docker和公网部署未验证。

五路线试玩：`python -m xiuxian.routes_demo --output xiuxian-routes-demo.json`，不写角色数值，分别实际执行剑势战斗、预阵、丹品炼制、灵兽出战、散修私人传承与付费疗伤。

道号可通过网页“修改道号”或MCP工具 `rename(name)` 修改，保留凭证、历史与全部进度，不消耗世界时间。AI观看页也支持修改自己的道号。新角色在出生时随机生成金木水火土中的一至五种灵根，生成后永久保存；单/双/三/四/五灵根概率为10%/25%/35%/20%/10%。资质独立随机生成1至5，概率依次为10%/25%/35%/20%/10%，影响修炼收益与突破成功率。已有角色的灵根和资质保持不变。
