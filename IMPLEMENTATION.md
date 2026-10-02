# 改造报告

本地基于 https://github.com/chloemeadow0-code/huogewoci 的 main 分支克隆直接修改，保留仓库Git历史；没有另建独立项目。尚未部署公网。

## 原架构分析

- `src/lorekit` 是通用基础：SQLite schema、sessions/session_meta、角色/区域表、叙事时间、NPC记忆、快照和分支存档。
- `src/hogwarts/engine.py` 原来加载 `systems/hogwarts` 的 world/spells/courses/items JSON，校园扩展状态以 `hogwarts_state` JSON 放在 session_meta，players按凭证派生的player_key隔离。
- `server.py` 用 FastMCP 暴露18个白名单工具，stdio入口和HTTP入口共用Game.call。原玩家MCP没有resources/prompts，管理员LoreKit工具不暴露给玩家。
- `auth.py` 只持久化凭证SHA256摘要，ContextVar隔离请求身份。
- `http_app.py` 复用单进程RLock、线程池、每请求SQLite连接，提供注册、状态、动作、健康检查、静态网页、Streamable HTTP。保留域名/来源校验、凭证类型隔离、POST大小限制和安全响应头。
- 原版没有完整战斗，也没有玩家端AI裁判入口；其魔咒、课程和物品结果原本已用规则计算。改造增加程序战斗，不是将AI判定代码换一个提示词。

## 保留与替换

保留整个 `src/lorekit`、LICENSE/NOTICE、数据库schema和快照工具。复用原账号摘要认证、请求身份隔离、MCP调用封装、HTTP权限边界、静态资源布局、Docker持久卷与容器降权机制。
将校园规则、课表、学院、魔杖、魔咒、宵禁、校园网页及测试替换为修仙模型、固定技能配置、四区域、四境界和回合战斗。玩家游戏模块改名为xiuxian，原hogwarts专属文件删除。新的成长和战斗规则集中在引擎，接口只传行动参数。

## 新增文件

- `src/xiuxian/__init__.py`：模块说明。
- `src/xiuxian/engine.py`：23个动作、状态持久化、时间事件、战斗、关系、任务、突破、秘境防刷。
- `src/xiuxian/rules.py`：校验、伤害、命中、逃跑公式。
- `src/xiuxian/models.py`：Player/StatusEffect/Technique/Skill/NPC/Quest类型。
- `src/xiuxian/auth.py`：复用原凭证机制，修仙凭证前缀xx_sk_。
- `src/xiuxian/server.py`：23工具、xiuxian://rules资源、begin_journey prompt。
- `src/xiuxian/http_app.py`：复用HTTP入口和身份边界，改为修仙状态。
- `src/xiuxian/container.py`：复用容器数据卷权限处理和降权。
- `src/xiuxian/operator.py`：复用LoreKit本地手动存档，不暴露给AI。
- `src/xiuxian/demo.py`：仅调用玩家动作的完整成长Demo。
- `src/xiuxian/web/index.html`、`app.js`、`style.css`、`manual.html`：注册、凭证与说明页。
- `systems/xiuxian/content.json`：境界、地图节点、功法、招式、NPC、敌人、掉落、物品、价格、配方、任务、事件和状态类型。
- `systems/xiuxian/requirements-deploy.txt`：沿用原部署锁定依赖。
- `tests/xiuxian/test_game.py`：规则、循环、随机重放、并发、恢复、状态、突破和防刷。
- `tests/xiuxian/test_protocol.py`：真实stdio和HTTP MCP、资源、prompt、角色隔离和完整循环重放。
- `run-xiuxian.py`、`start-xiuxian.ps1`：沿用原启动方式。
- `.github/workflows/xiuxian-deploy.yml`：沿用原Linux测试、Docker构建与卷恢复检查，切换模块和接口。
- `IMPLEMENTATION.md`：本报告。

修改：README.md、DEPLOY.md、Dockerfile、compose.yaml、.dockerignore、.gitignore。删除：src/hogwarts、systems/hogwarts、tests/hogwarts、HOGWARTS.md、run-hogwarts.py、start-hogwarts.ps1及旧工作流。

## 可玩内容与循环

详细ID和调用示例见README。世界为按身份映射的宗门驻地、青石镇、落霞山野和灵溪秘境；4名NPC、6种敌人、9门功法、13个固定类型招式、31种物品、9个配方、13个任务。炼气、筑基、金丹、元婴各初中后期与圆满。

MCP工具：get_self / get_world / cultivate / travel / explore / talk / fight / use_skill / use_item / craft / trade / accept_quest / submit_quest / breakthrough / retreat / inspect_history / choose_route / inspect_route / learn_technique / prepare_formation / manage_beast / track / rename。

可以真实完成：入宗→修炼→采药任务→下山探索→妖兽逐回合战斗→掉落→回宗交任务→学功法/买装备→炼气圆满→筑基丹→筑基→进入周期秘境→击败石卫→交试炼任务。Demo不会写角色数值或赠送测试物品。

## 权威规则与存储

AI只传招式ID和行动参数。命中、伤害、控制、先后手、冷却、灵力、掉落和突破由程序计算；不存在描述解析、LLM裁判或任意效果/数值参数。
攻击公式：max(1, 威力×有效攻击/100 + 3×境界差 − 有效防御)，之后护盾吸收。敏捷影响先手、命中与逃跑。可重放PRNG存入世界，随机用途与结果写历史。失败动作回滚所有资源、时间和随机状态。

`accounts.db`仅凭证摘要及身份；`xiuxian.db`沿用LoreKit SQLite，sessions/system_type=xiuxian，session_meta/key=xiuxian_state保存版本化世界与独立玩家JSON。世界分钟、事件、PRNG、秘境周期和个人完整历史持久化；失败不会立即死亡，重伤和物品掉落需疗养。

## 验证与限制

测试报告和Demo结果作为交付附件提供。测试覆盖真实MCP、完整筑基与秘境循环、四境界突破、失败代价、秘境周期、防重复奖励、装备、非法参数、账号隔离、并发不丢动作、重启恢复和原LoreKit快照恢复。

本机未安装Docker，未实际验证Docker构建、Linux工作流或公网部署。工作流已经更新，不能把旧仓库的CI成功结果当作本次改造验证。

第一版仍简化：单进程共享行动时钟；出生随机生成并持久化五行灵根组合与1至5资质；区域内节点没有逐建筑专属规则；NPC使用固定选项与记忆；部分世界事件只修改规则参数，拍卖会没有竞价；高境界缺少专属地图；暂无跨玩家交易、多人战斗、宗门竞争、实时后台时钟、真正死亡和转世。旧校园存档与hw_sk_凭证不自动迁移，部署建议新数据目录。

本次 Windows / Python 3.12 验证：82项测试全部通过，含真实stdio完整循环重放和Streamable HTTP认证；独立Demo完成筑基、秘境石卫与任务提交。Docker和公网部署未验证。

## 五路线增量改造

新增 src/xiuxian/routes.py（路线配置与规则助手）、routes_demo.py（五种玩法试玩）、tests/xiuxian/test_routes.py、ROUTES.md。
修改 engine.py 将原规则计算接入路线修正、预阵、剑势、丹品、灵兽、信誉与方向成长；server.py增加choose_route/inspect_route/learn_technique/prepare_formation/manage_beast/track，总计23工具。
修改 content.json 保存完整五条路线设定与资源、专属传承/技能/任务、预阵、丹品、灵兽和价格参数；models.py新增路线与灵兽类型；http_app.py及注册页支持可选route，未选择时AI自主择道；demo.py改为剑宗路线，并根据状态主动补给。
旧版修仙存档不清空，第一次选择路线后不能再切换。新角色必须择道才能开始行动。四区域结构保留，宗门驻地按身份显示，散修以小镇为基地。

固定加成负面与四种宗门机制、散修杂学已由程序实现。功法等级与熟练度数值成长已经实现。组队门规、宗门政治、科研审批和真正死亡仍未实现，详见ROUTES.md；不存在AI临场裁定。

本次最终验证：82项测试全部通过；原筑基/秘境Demo与五路线独立试玩均完成。包含真实stdio完整成长重放、HTTP MCP、旧存档择道、路线特殊机制与价格一致性。

新增birth.py：灵根与资质出生抽样使用系统随机源，与战斗随机序列隔离；旧存档不重抽。rename动作保留人物ID、凭证、全部进度与关系，只记录改名历史，不推进时间。网页人类与AI凭证均可通过/api/rename修改自己的道号。
