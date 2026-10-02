# 灵汐岛第一版交付清单

基于现有青云问道直接升级，旧账号、道号、境界、随机出生属性和库存保留。本文列出当前代码实际实现；数值以 `systems/xiuxian/content.json`、`island.json`、`rules.py/engine.py/routes.py/island.py` 为准。

## 目录

```text
src/xiuxian/
  engine.py routes.py rules.py birth.py models.py
  db.py island.py auth.py mcp_dispatch.py server.py http_app.py
  operator.py container.py island_demo.py
  web/{index.html,manual.html,style.css,app.js,api.js,store.js,map.js,hud.js,catalog.js}
  web/scenes/place.js  web/ui/{dom.js,modal.js}
systems/xiuxian/{content.json,island.json,requirements-deploy.txt}
tests/xiuxian/  third_party/allotment-relay/LICENSE
run-xiuxian.py start-xiuxian.ps1 Dockerfile compose.yaml
```

框架复用/修改文件详见 IMPLEMENTATION.md。潮汐岛生活业务未导入，无作物、捕鱼、婚姻、剧场等改名映射。

## 数据库

`accounts.db` 使用 `api_keys`，只保存凭证摘要与角色身份。`xiuxian.db` 使用下列独立表：

`world_state`, `cultivators`, `cultivator_stats`, `cultivator_meta`, `cultivator_inventory`, `cultivator_equipment`, `cultivator_techniques`, `cultivator_skills`, `cultivator_status`, `npc_relationships`, `quest_progress`, `histories`, `world_events`, `world_flags`, `world_logs`, `incidents`, `item_ledgers`, `battles`, `battle_turns`, `spirit_beasts`, `sect_members`, `sect_reputation`, `event_rolls`, `exploration_logs`, `market_listings`, `quests`, `snapshots`, `idempotency`, `migrations`.


角色身份/地点在 cultivators；数值在 cultivator_stats；背包、装备、功法、技能、状态、关系、任务分别独立。API 提供 name/sect/realm/realm_stage/cultivation/cultivation_required/hp/max_hp/qi/max_qi/spirit/strength/agility/defense/aptitude/spirit_root/location/reputation/sect_reputation/money/inventory/equipment/techniques/skills/quests/relationships/status_effects/injuries，历史由 history 子命令分页查询。为旧规则复用，SQL 部分字段保留 maxQi/stage/stones 等命名，API 同时提供新别名。

WAL、30 秒 busy_timeout、BEGIN IMMEDIATE、进程 RLock；MCP/v1 外层最多 5 次锁重试。资源扣除、随机序列、奖励和成功请求缓存同事务；重复编号不重复获得收益，编号改参数会拒绝。管理员 snapshots 独立于实时存档；完整备份还要保存 accounts.db。

## MCP 工具与全部子命令

relay_manual 返回全局手册，不修改状态。其余工具支持 help，ID 或唯一精确名称，名称含空格时加引号。参数越界、额外文本、未知技能和不具备的材料都会拒绝。


| 工具 | command |
| --- | --- |
| relay_manual | 无参数，全局手册 |
| cultivator_ops | sheet; rename <道号>; history [1–50]; incidents; resolve <编号> <care / materials / self> |
| sect_ops | status; join <qingxiao / xuanheng / danxia / fuyao / rogue>; task list; task accept <任务>; task step <任务> [分支]; task submit <任务> |
| cultivate_ops | status; meditate [1–72小时]; method <功法> [小时]; retreat [小时]; learn <功法>; ask <NPC> |
| travel_ops | map; go <地点> [节点]; explore |
| battle_ops | status; fight <附近敌人>; skill <已学技能>; item <物品>; retreat; formation <ward / snare / gather / kill> |
| bag_ops | list; use <物品>; equip <法器>; ledger [物品] |
| refine_ops | list; pill <配方/物品> [数量]; weapon <配方/物品> [数量]; craft <配方> [数量] |
| npc_ops | list; talk <NPC> [greeting / quest / teach / rumor / help / insult / spar]; gift <NPC> <物品>; beast <contract [种类] / feed / heal / stance [assist / rest / forced] / release / abuse / train>; track <敌人> |
| quest_ops | list; accept <任务>; step <任务> [report / protect]; submit <任务> |
| market_ops | list; buy <物品> [数量]; sell <物品> [数量]; auction; bid <拍品ID> <灵石> |
| realm_ops | status; breakthrough; enter; leave |
| world_ops | status; log [1–50]; incidents; resolve <编号> <care / materials / self> |


| 工具 | 默认/示例/约束 |
| --- | --- |
| cultivator_ops | 身份与个人记录。空=sheet。sheet；rename 云游客；history 20；incidents；resolve 1 care。改名不改凭证、信誉或出生属性。 |
| sect_ops | 宗门与路线。空=status。status；join qingxiao；task list；task accept trial_qingxiao；task step trial_qingxiao report；task submit trial_qingxiao。只能选择一次路线；散修join rogue。 |
| cultivate_ops | 修炼与长期功法。空=status。meditate 4；method qingxiao_sword 4；retreat 8；learn qingxiao_sword；ask 林青枝。单位游戏小时，不是现实等待；功法与技能分开。 |
| travel_ops | 山海行路。空=map。map；go 青竹林；go 潮生秘境 古殿；explore。只能沿相邻出口；筑基解锁高级区域。 |
| battle_ops | 逐回合斗法。空=status。fight wolf；skill 青云剑诀；item 回气丹；retreat；formation ward。fight只开战；技能效果来自固定配置，禁止追加数值。 |
| bag_ops | 背包、装备与履历。空=list。list；use 回气丹；equip 青云剑；ledger 青云剑。use/equip只使用已持有物品。 |
| refine_ops | 炼丹炼器与制符。空=list。list；pill 回气丹 2；weapon 青云剑 1；craft paper_talisman 1。检查功法、境界、材料，结果由代码判定。 |
| npc_ops | 附近人物与关系。空=list。list；talk 林青枝；talk 林青枝 teach；gift 林青枝 灵草；beast contract cloud_fox；beast feed；beast train；track wolf。人类与AI共用关系和灵兽。 |
| quest_ops | 阶段任务。空=list。list；accept trial_qingxiao；step trial_qingxiao；step trial_qingxiao report；submit trial_qingxiao。阶段必须由实际行动达成；终幕report/protect二选一。 |
| market_ops | 灵石交易与竞价。空=list。list；buy 回气丹 1；sell 灵草 2；auction；bid auction:0 50。竞价托管，到期交付，被超价退还。黑市须亲自前往。 |
| realm_ops | 境界与潮生秘境。空=status。status；breakthrough；enter；leave。突破检查修为、状态、功法及材料，失败有记录和处置。 |
| world_ops | 世界变化和灾档闭环。空=status。status；log 20；incidents；resolve 1 materials。未处理坏事会持续限制相应行动；处置cost和success见灾档。 |


资源 `xiuxian://rules` 返回配置；prompt `begin_journey` 提供初始行动提示。原 get_self/get_world/cultivate/travel/explore/talk/fight/use_skill/use_item/craft/trade/accept_quest/submit_quest/breakthrough/retreat/inspect_history 留在内部规则路由，外部 MCP 使用对应聚合工具，避免几十个碎工具。

## 地图


| ID | 地点 | 出口 | 门槛 |
| --- | --- | --- | --- |
| qingxiao | 青霄剑宗 | market, bamboo | 0 |
| xuanheng | 玄衡阵门 | market, ruins | 0 |
| danxia | 丹霞谷 | market, mist | 0 |
| fuyao | 伏妖门 | market, ridge | 0 |
| market | 灵汐坊市 | qingxiao, xuanheng, danxia, fuyao, blackmarket, bamboo, lake | 0 |
| blackmarket | 黑市巷 | market, ruins | 0 |
| bamboo | 青竹林 | market, qingxiao, mist | 0 |
| mist | 雾隐山谷 | bamboo, danxia, lake | 0 |
| ridge | 荒岭深处 | fuyao, lake | 1 |
| lake | 月汐湖 | market, mist, ridge, secret | 1 |
| ruins | 旧宗遗址 | blackmarket, xuanheng, secret | 1 |
| secret | 潮生秘境 | lake, ruins | 1 |

灵汐坊市是中心。门槛 0 为炼气，1 为筑基；只能沿相邻出口移动。潮生秘境还检查开放窗口及当周进入记录。

## 宗门和散修


| 路线 | 固定加成与代价 | 机制 |
| --- | --- | --- |
| 青霄剑宗 | 剑伤+12%；战斗熟练度+15%；战斗任务声望+20%；生产成长−10%；非剑效果−5% | 两次连续主动攻击且未受控，下一攻击命中+10百分点/伤害+10%，使用后消耗 |
| 玄衡阵门 | 阵符机关+15%；破解+20百分点；异常发现+15百分点；突发首轮伤害−10%；阵机关耗材+10% | 主动开战可消耗材料预置一种护/困/聚灵/杀阵，突然遭遇不生效 |
| 丹霞谷 | 丹效+20%；治疗+15%；额外灵草概率+15百分点；炼丹成功+10百分点；攻击−8%；锻造成功−10百分点 | 普通/良品/上品；越级可废丹或炸炉 |
| 伏妖门 | 对妖兽伤害+12%；野外受伤概率−15百分点；追踪+20百分点；灵兽成长+20%；城镇价格+5%；炼丹成功−8百分点 | 契约一只主要独立灵兽，培养和伤病影响出战及忠诚 |
| 散修 | 跨流派惩罚减半；奇遇+15百分点；黑市特殊出现+15百分点；突破材料+15%；购买+8% | 最多四主方向；方向越多成长越慢；无免费客舍疗养；信誉跨地图保存 |

各宗背景、门规和资源直接保留在 content.routes。组队、完整门规执法等未实现部分见末尾。

## 正常 NPC（18）


| ID | 姓名/身份 | 地点 | 职责/功能 | 性格 | 个人任务 |
| --- | --- | --- | --- | --- | --- |
| qingxiao_leader | 闻照川 / 掌门 | 青霄剑宗 | 调停与传承 / talk,story | 沉稳克制 | personal_qingxiao_leader |
| qingxiao_mentor | 林青枝 / 核心导师 | 青霄剑宗 | 功法指导 / talk,teach,quest | 爽朗耐心 | personal_qingxiao_mentor |
| qingxiao_steward | 许听风 / 事务负责人 | 青霄剑宗 | 任务与资源 / talk,quest,shop | 严谨可靠 | personal_qingxiao_steward |
| xuanheng_leader | 顾衡 / 掌门 | 玄衡阵门 | 调停与传承 / talk,story | 安静理性 | personal_xuanheng_leader |
| xuanheng_mentor | 沈知序 / 核心导师 | 玄衡阵门 | 功法指导 / talk,teach,quest | 好奇细致 | personal_xuanheng_mentor |
| xuanheng_steward | 柳未央 / 事务负责人 | 玄衡阵门 | 任务与资源 / talk,quest,shop | 谨慎认真 | personal_xuanheng_steward |
| danxia_leader | 苏映霞 / 掌门 | 丹霞谷 | 调停与传承 / talk,story | 温和坚定 | personal_danxia_leader |
| danxia_mentor | 温芷 / 核心导师 | 丹霞谷 | 功法指导 / talk,teach,quest | 细腻坦率 | personal_danxia_mentor |
| danxia_steward | 叶小满 / 事务负责人 | 丹霞谷 | 任务与资源 / talk,quest,shop | 开朗忙碌 | personal_danxia_steward |
| fuyao_leader | 陆山眠 / 掌门 | 伏妖门 | 调停与传承 / talk,story | 宽厚寡言 | personal_fuyao_leader |
| fuyao_mentor | 白若岚 / 核心导师 | 伏妖门 | 功法指导 / talk,teach,quest | 清醒耐心 | personal_fuyao_mentor |
| fuyao_steward | 石望 / 事务负责人 | 伏妖门 | 任务与资源 / talk,quest,shop | 认真警惕 | personal_fuyao_steward |
| merchant | 岑小舟 / 坊市商人 | 灵汐坊市 | 辨认法器真伪 / talk,shop | 健谈 | personal_merchant |
| innkeeper | 桑晚 / 客栈老板 | 灵汐坊市 | 疗伤与落脚 / talk,heal | 温和 | personal_innkeeper |
| alliance | 赵行远 / 散修盟管事 | 灵汐坊市 | 私人传承与委托 / talk,teach,quest | 务实 | personal_alliance |
| intel | 云栖 / 情报贩子 | 黑市巷 | 辨别危险线索 / talk,quest | 敏锐 | personal_intel |
| blackmerchant | 阿朔 / 黑市商人 | 黑市巷 | 特殊货物与拍卖 / talk,shop,quest | 机灵 | personal_blackmerchant |
| guide | 程见山 / 遗迹向导 | 旧宗遗址 | 探路与禁制指引 / talk,quest | 耐心 | personal_guide |

每人还配置背景、优缺点、好感/信任/敌意、特殊事件。问候、赠礼和冒犯修改关系；传授检查导师和路线；信任达标的特殊事件只触发一次并持久化。

## 敌对人物（6）


| ID | 人物/身份 | 势力 | 目的 | 活动范围 |
| --- | --- | --- | --- | --- |
| bloodmaster | 殷迟 / 血炼堂堂主 | 血炼堂 | 夺取灵脉，换取病中弟子的寿命 | mist |
| exile | 周落星 / 青霄剑宗弃徒 | 离宗剑修 | 证明被否定的禁剑，却不愿伤害当年的同门 | bamboo |
| owner | 闻既白 / 黑市幕后东家 | 黑市债契 | 垄断残卷来历，以旧债控制商人 | blackmarket |
| oldhunter | 秦逐 / 伏妖门前猎妖统领 | 猎杀派旧部 | 消灭曾毁掉边寨的妖群，拒绝区分契约兽 | ridge |
| poisoner | 祝眠 / 丹霞谷禁药师 | 离谷药师 | 证明禁药能够救人，隐瞒失败者的代价 | mist |
| remnant | 沈潮生 / 古秘境残魂宗主 | 旧宗残魂 | 保住旧宗弟子的残念，让开阵者承担代价 | secret |

都有独立阶段任务和世界标记；调查推进后影响活动区探索伤害，终幕解除该阶段影响。当前剧情由配置和分支规则展开。

## 功法


| ID | 名称 | 类型 | 境界门槛 | 修炼加值/灵力加值 | 被动 |
| --- | --- | --- | --- | --- | --- |
| basic_meditation | 青云吐纳诀 | 心法 | 0 | 0 / 0 | {} |
| verdant | 长春功 | 心法 | 0 | 3 / 10 | {'regeneration': 1} |
| sword_art | 青云剑经 | 剑诀 | 1 | 2 / 5 | {'strength': 3} |
| qingxiao_sword | 断云剑心诀 | 剑诀 | 0 | 1 / 5 | {} |
| xuanheng_array | 玄衡阵解 | 阵诀 | 0 | 2 / 5 | {} |
| danxia_herbal | 丹霞药经 | 丹道 | 0 | 2 / 5 | {} |
| fuyao_body | 伏妖锻体经 | 体修 | 0 | 1 / 5 | {} |
| beast_lore | 驭兽残卷 | 御兽 | 0 | 0 / 5 | {} |
| forbidden_sword | 禁录·噬魂剑 | 剑诀 | 0 | 2 / 0 | {'strength': 2} |
| talisman_manual | 听雨符经 | 符道 | 0 | 1 / 5 | {} |
| forge_manual | 温炉器录 | 器道 | 0 | 1 / 5 | {'defense': 1} |

功法与招式分开，当前功法影响长期成长、灵力和被动；学习检查境界、学费、传承资格、主方向上限。功法等级由真实熟练度提高。

## 固定技能


| ID | 名称 | 类别 | 灵力/冷却 | 威力/命中 | 效果/概率/持续 | 境界 |
| --- | --- | --- | --- | --- | --- | --- |
| strike | 青云剑诀 | attack | 0/0 | 100/95 | 类别默认/100/2 | 0 |
| guard | 磐石诀 | defense | 3/1 | 12/95 | 类别默认/100/2 | 0 |
| heal | 回春诀 | heal | 6/2 | 18/95 | 类别默认/100/2 | 0 |
| bind | 缚灵诀 | control | 8/3 | 1/95 | 类别默认/100/2 | 0 |
| haste | 御风诀 | buff | 4/2 | 6/95 | 类别默认/100/2 | 0 |
| poison | 毒藤术 | debuff | 6/2 | 3/90 | poison/90/3 | 0 |
| dash | 流云步 | movement | 4/2 | 8/100 | haste/100/2 | 0 |
| escape | 遁光术 | escape | 5/1 | 20/100 | 类别默认/100/1 | 0 |
| sword_burst | 断云斩 | attack | 8/1 | 150/95 | 类别默认/100/2 | 0 |
| array_bolt | 阵旗·穿山 | attack | 5/1 | 120/95 | 类别默认/100/2 | 0 |
| mechanical_bolt | 机关连弩 | attack | 3/1 | 110/95 | 类别默认/100/2 | 0 |
| talisman_shield | 护身符 | defense | 4/1 | 15/95 | 类别默认/100/2 | 0 |
| body_strike | 伏妖拳 | attack | 3/1 | 120/95 | 类别默认/100/2 | 0 |
| calm | 清心诀 | buff | 4/2 | 4/95 | 类别默认/80/2 | 0 |
| weaken | 落叶诀 | debuff | 5/2 | 2/95 | weakness/80/2 | 0 |
| escape_step | 归风步 | escape | 4/2 | 15/95 | 类别默认/80/2 | 0 |

配置 cost/type/effectChance 对应 qi_cost/category/effect_chance。buff/movement 当前提高灵敏；debuff/control 使用固定状态。所有技能八类别齐全，不存在自然语言招式裁判。

## 灵兽


| ID | 名称 | 性格 | 初始气血 | 技能 |
| --- | --- | --- | --- | --- |
| cloud_fox | 云狐 | 谨慎 | 45 | strike,guard |
| stone_ape | 岩猿 | 勇猛 | 60 | strike,guard |

独立 spirit_beasts 表保存种类、名字、等级、气血、忠诚、性格、状态及完整灵兽结构；包括技能、伤势、饥饿、契约主人。可契约、喂养、治疗、训练、助战/休养/强迫和登记解除。训练需4灵石；三级可学习护卫，五级灵性觉醒；虐待、伤势和资源缺乏可能失去忠诚/离开。第一版进化为属性与标记，未做独立进化树。

## 物品与配方


| ID | 物品 | 类型 | 效果 | 基础价 |
| --- | --- | --- | --- | --- |
| herb | 灵草 | 灵药 | {} | 4 |
| potion | 回气丹 | 丹药 | {'hp': 40, 'qi': 20} | 12 |
| foundation_pill | 筑基丹 | 丹药 | {} | 80 |
| golden_pill | 结金丹 | 丹药 | {} | 150 |
| soul_pill | 凝婴丹 | 丹药 | {} | 250 |
| iron | 玄铁 | 材料 | {} | 8 |
| core | 灵核 | 材料 | {} | 30 |
| fang | 狼牙 | 材料 | {} | 6 |
| sword | 青云剑 | 法器 | {'strength': 8} | 40 |
| armor | 玄铁甲 | 法器 | {'defense': 5} | 35 |
| charm | 清心佩 | 法器 | {'spirit': 4} | 25 |
| talisman | 护身法宝 | 法器 | {'defense': 3} | 40 |
| manual | 长春功卷 | 功法 | {} | 25 |
| sword_manual | 青云剑经 | 功法 | {} | 不常售 |
| array_flag | 阵旗 | 材料 | {} | 4 |
| paper_talisman | 基础符箓 | 材料 | {} | 3 |
| mechanism_part | 机关零件 | 材料 | {} | 4 |
| scrap | 废丹 | 杂物 | {} | 1 |
| relic_fragment | 遗迹残片 | 材料 | {} | 20 |
| forbidden_sword | 禁录邪剑残卷 | 功法 | {} | 80 |
| forbidden_pill | 禁丹 | 丹药 | {} | 60 |
| protected_core | 保护种群兽核 | 材料 | {} | 60 |
| potion_fine | 回气丹·良品 | 丹药 | {'hp': 40, 'qi': 20} | 16 |
| potion_superior | 回气丹·上品 | 丹药 | {'hp': 40, 'qi': 20} | 24 |
| foundation_pill_fine | 筑基丹·良品 | 丹药 | {} | 112 |
| foundation_pill_superior | 筑基丹·上品 | 丹药 | {} | 160 |
| golden_pill_fine | 结金丹·良品 | 丹药 | {} | 210 |
| golden_pill_superior | 结金丹·上品 | 丹药 | {} | 300 |
| soul_pill_fine | 凝婴丹·良品 | 丹药 | {} | 350 |
| soul_pill_superior | 凝婴丹·上品 | 丹药 | {} | 500 |
| core_array_chart | 玄衡核心阵图 | 功法 | {} | 80 |


| 配方/产物 | 消耗 |
| --- | --- |
| potion | {'herb': 2} |
| foundation_pill | {'herb': 5, 'core': 1} |
| sword | {'iron': 3} |
| golden_pill | {'herb': 8, 'core': 2} |
| soul_pill | {'herb': 12, 'core': 3} |
| armor | {'iron': 3} |
| array_flag | {'iron': 1} |
| paper_talisman | {'herb': 1} |
| mechanism_part | {'iron': 1} |

普通材料只计库存；法器、功法物品、高品质丹药、突破丹、灵兽蛋拥有逐件获得/消费/出售履历。拍卖托管灵石，被超价原买方退款，到游戏时间截止交付，重复请求不重复扣款。旧存档物品不编造其迁移前来源。

## 阶段任务（30）


| ID | 名称 | 接取/交付地点 | 阶段 | 奖励/声望/贡献 |
| --- | --- | --- | --- | --- |
| trial_qingxiao | 山门初历 | qingxiao | {'type': 'talk', 'npc': 'qingxiao_mentor', 'label': '向导师请教'} → {'type': 'kill', 'target': 'wolf', 'location': 'bamboo', 'label': '巡守青竹林，击退一只妖狼'} → {'type': 'return', 'location': 'qingxiao', 'label': '回山门报告'} | 65/8/10 |
| trial_xuanheng | 山门初历 | xuanheng | {'type': 'talk', 'npc': 'xuanheng_mentor', 'label': '向导师请教'} → {'type': 'kill', 'target': 'wolf', 'location': 'bamboo', 'label': '巡守青竹林，击退一只妖狼'} → {'type': 'return', 'location': 'xuanheng', 'label': '回山门报告'} | 65/8/10 |
| trial_danxia | 山门初历 | danxia | {'type': 'talk', 'npc': 'danxia_mentor', 'label': '向导师请教'} → {'type': 'kill', 'target': 'wolf', 'location': 'bamboo', 'label': '巡守青竹林，击退一只妖狼'} → {'type': 'return', 'location': 'danxia', 'label': '回山门报告'} | 65/8/10 |
| trial_fuyao | 山门初历 | fuyao | {'type': 'talk', 'npc': 'fuyao_mentor', 'label': '向导师请教'} → {'type': 'kill', 'target': 'wolf', 'location': 'bamboo', 'label': '巡守青竹林，击退一只妖狼'} → {'type': 'return', 'location': 'fuyao', 'label': '回山门报告'} | 65/8/10 |
| rogue_trial | 一位散修的第一步 | market | {'type': 'talk', 'npc': 'alliance', 'label': '拜访散修盟'} → {'type': 'explore', 'location': 'bamboo', 'count': 1, 'label': '探索青竹林'} → {'type': 'return', 'location': 'market', 'label': '报告新发现'} | 65/8/10 |
| personal_qingxiao_leader | 闻照川的旧事 | qingxiao | {'type': 'talk', 'npc': 'qingxiao_leader', 'label': '听一段旧事'} → {'type': 'explore', 'location': 'bamboo', 'count': 1, 'label': '亲自查看线索'} → {'type': 'return', 'location': 'qingxiao', 'label': '回去商议'} | 30/8/10 |
| personal_qingxiao_mentor | 林青枝的旧事 | qingxiao | {'type': 'talk', 'npc': 'qingxiao_mentor', 'label': '听一段旧事'} → {'type': 'explore', 'location': 'bamboo', 'count': 1, 'label': '亲自查看线索'} → {'type': 'return', 'location': 'qingxiao', 'label': '回去商议'} | 30/8/10 |
| personal_qingxiao_steward | 许听风的旧事 | qingxiao | {'type': 'talk', 'npc': 'qingxiao_steward', 'label': '听一段旧事'} → {'type': 'explore', 'location': 'bamboo', 'count': 1, 'label': '亲自查看线索'} → {'type': 'return', 'location': 'qingxiao', 'label': '回去商议'} | 30/8/10 |
| personal_xuanheng_leader | 顾衡的旧事 | xuanheng | {'type': 'talk', 'npc': 'xuanheng_leader', 'label': '听一段旧事'} → {'type': 'explore', 'location': 'ruins', 'count': 1, 'label': '亲自查看线索'} → {'type': 'return', 'location': 'xuanheng', 'label': '回去商议'} | 30/8/10 |
| personal_xuanheng_mentor | 沈知序的旧事 | xuanheng | {'type': 'talk', 'npc': 'xuanheng_mentor', 'label': '听一段旧事'} → {'type': 'explore', 'location': 'ruins', 'count': 1, 'label': '亲自查看线索'} → {'type': 'return', 'location': 'xuanheng', 'label': '回去商议'} | 30/8/10 |
| personal_xuanheng_steward | 柳未央的旧事 | xuanheng | {'type': 'talk', 'npc': 'xuanheng_steward', 'label': '听一段旧事'} → {'type': 'explore', 'location': 'ruins', 'count': 1, 'label': '亲自查看线索'} → {'type': 'return', 'location': 'xuanheng', 'label': '回去商议'} | 30/8/10 |
| personal_danxia_leader | 苏映霞的旧事 | danxia | {'type': 'talk', 'npc': 'danxia_leader', 'label': '听一段旧事'} → {'type': 'explore', 'location': 'mist', 'count': 1, 'label': '亲自查看线索'} → {'type': 'return', 'location': 'danxia', 'label': '回去商议'} | 30/8/10 |
| personal_danxia_mentor | 温芷的旧事 | danxia | {'type': 'talk', 'npc': 'danxia_mentor', 'label': '听一段旧事'} → {'type': 'explore', 'location': 'mist', 'count': 1, 'label': '亲自查看线索'} → {'type': 'return', 'location': 'danxia', 'label': '回去商议'} | 30/8/10 |
| personal_danxia_steward | 叶小满的旧事 | danxia | {'type': 'talk', 'npc': 'danxia_steward', 'label': '听一段旧事'} → {'type': 'explore', 'location': 'mist', 'count': 1, 'label': '亲自查看线索'} → {'type': 'return', 'location': 'danxia', 'label': '回去商议'} | 30/8/10 |
| personal_fuyao_leader | 陆山眠的旧事 | fuyao | {'type': 'talk', 'npc': 'fuyao_leader', 'label': '听一段旧事'} → {'type': 'explore', 'location': 'ridge', 'count': 1, 'label': '亲自查看线索'} → {'type': 'return', 'location': 'fuyao', 'label': '回去商议'} | 30/8/10 |
| personal_fuyao_mentor | 白若岚的旧事 | fuyao | {'type': 'talk', 'npc': 'fuyao_mentor', 'label': '听一段旧事'} → {'type': 'explore', 'location': 'ridge', 'count': 1, 'label': '亲自查看线索'} → {'type': 'return', 'location': 'fuyao', 'label': '回去商议'} | 30/8/10 |
| personal_fuyao_steward | 石望的旧事 | fuyao | {'type': 'talk', 'npc': 'fuyao_steward', 'label': '听一段旧事'} → {'type': 'explore', 'location': 'ridge', 'count': 1, 'label': '亲自查看线索'} → {'type': 'return', 'location': 'fuyao', 'label': '回去商议'} | 30/8/10 |
| personal_merchant | 岑小舟的旧事 | market | {'type': 'talk', 'npc': 'merchant', 'label': '听一段旧事'} → {'type': 'explore', 'location': 'bamboo', 'count': 1, 'label': '亲自查看线索'} → {'type': 'return', 'location': 'market', 'label': '回去商议'} | 30/8/10 |
| personal_innkeeper | 桑晚的旧事 | market | {'type': 'talk', 'npc': 'innkeeper', 'label': '听一段旧事'} → {'type': 'explore', 'location': 'bamboo', 'count': 1, 'label': '亲自查看线索'} → {'type': 'return', 'location': 'market', 'label': '回去商议'} | 30/8/10 |
| personal_alliance | 赵行远的旧事 | market | {'type': 'talk', 'npc': 'alliance', 'label': '听一段旧事'} → {'type': 'explore', 'location': 'bamboo', 'count': 1, 'label': '亲自查看线索'} → {'type': 'return', 'location': 'market', 'label': '回去商议'} | 30/8/10 |
| personal_intel | 云栖的旧事 | blackmarket | {'type': 'talk', 'npc': 'intel', 'label': '听一段旧事'} → {'type': 'explore', 'location': 'ruins', 'count': 1, 'label': '亲自查看线索'} → {'type': 'return', 'location': 'blackmarket', 'label': '回去商议'} | 30/8/10 |
| personal_blackmerchant | 阿朔的旧事 | blackmarket | {'type': 'talk', 'npc': 'blackmerchant', 'label': '听一段旧事'} → {'type': 'explore', 'location': 'ruins', 'count': 1, 'label': '亲自查看线索'} → {'type': 'return', 'location': 'blackmarket', 'label': '回去商议'} | 30/8/10 |
| personal_guide | 程见山的旧事 | ruins | {'type': 'talk', 'npc': 'guide', 'label': '听一段旧事'} → {'type': 'explore', 'location': 'ruins', 'count': 1, 'label': '亲自查看线索'} → {'type': 'return', 'location': 'ruins', 'label': '回去商议'} | 30/8/10 |
| villain_bloodmaster | 追寻：殷迟 | blackmarket | {'type': 'talk', 'npc': 'intel', 'label': '核实传闻'} → {'type': 'explore', 'location': 'mist', 'count': 1, 'label': '搜集现场证据'} → {'type': 'kill', 'target': 'bloodmaster', 'location': 'mist', 'label': '阻止正在发生的危害'} → {'type': 'return', 'location': 'blackmarket', 'label': '决定如何处置'} | 80/8/10 |
| villain_exile | 追寻：周落星 | blackmarket | {'type': 'talk', 'npc': 'intel', 'label': '核实传闻'} → {'type': 'explore', 'location': 'bamboo', 'count': 1, 'label': '搜集现场证据'} → {'type': 'kill', 'target': 'exile', 'location': 'bamboo', 'label': '阻止正在发生的危害'} → {'type': 'return', 'location': 'blackmarket', 'label': '决定如何处置'} | 80/8/10 |
| villain_owner | 追寻：闻既白 | blackmarket | {'type': 'talk', 'npc': 'intel', 'label': '核实传闻'} → {'type': 'explore', 'location': 'blackmarket', 'count': 1, 'label': '搜集现场证据'} → {'type': 'kill', 'target': 'owner', 'location': 'blackmarket', 'label': '阻止正在发生的危害'} → {'type': 'return', 'location': 'blackmarket', 'label': '决定如何处置'} | 80/8/10 |
| villain_oldhunter | 追寻：秦逐 | blackmarket | {'type': 'talk', 'npc': 'intel', 'label': '核实传闻'} → {'type': 'explore', 'location': 'ridge', 'count': 1, 'label': '搜集现场证据'} → {'type': 'kill', 'target': 'oldhunter', 'location': 'ridge', 'label': '阻止正在发生的危害'} → {'type': 'return', 'location': 'blackmarket', 'label': '决定如何处置'} | 80/8/10 |
| villain_poisoner | 追寻：祝眠 | blackmarket | {'type': 'talk', 'npc': 'intel', 'label': '核实传闻'} → {'type': 'explore', 'location': 'mist', 'count': 1, 'label': '搜集现场证据'} → {'type': 'kill', 'target': 'poisoner', 'location': 'mist', 'label': '阻止正在发生的危害'} → {'type': 'return', 'location': 'blackmarket', 'label': '决定如何处置'} | 80/8/10 |
| villain_remnant | 追寻：沈潮生 | blackmarket | {'type': 'talk', 'npc': 'intel', 'label': '核实传闻'} → {'type': 'explore', 'location': 'secret', 'count': 1, 'label': '搜集现场证据'} → {'type': 'kill', 'target': 'remnant', 'location': 'secret', 'label': '阻止正在发生的危害'} → {'type': 'return', 'location': 'blackmarket', 'label': '决定如何处置'} | 80/8/10 |
| realm_journey | 潮生门前 | market | {'type': 'realm', 'realm': '筑基', 'label': '筑基'} → {'type': 'explore', 'location': 'secret', 'count': 1, 'label': '进入潮生秘境并探索'} → {'type': 'kill', 'target': 'remnant', 'location': 'secret', 'label': '面对古宗残魂'} → {'type': 'return', 'location': 'market', 'label': '将见闻带回岛上'} | 120/8/10 |

阶段目标由接受后的实际交谈、探索记录、击杀增量、位置及境界校验；终幕 report 如实报告或 protect 付5灵石善后、额外8灵石奖励。必须在交付地点完成所有阶段，不能自己宣称完成或重复领奖。旧已接委托保留内部兼容，新增任务统一用阶段表。

## 世界事件（13类）


| 事件配置 |
| --- |
| {'id': 'beast_tide', 'name': '妖兽潮', 'exploreDamage': 2} |
| {'id': 'realm_open', 'name': '秘境开放'} |
| {'id': 'herbs', 'name': '灵药成熟', 'extraHerb': 1} |
| {'id': 'tournament', 'name': '宗门试炼'} |
| {'id': 'auction', 'name': '坊市拍卖'} |
| {'id': 'black_trade', 'name': '黑市交易'} |
| {'id': 'rain', 'name': '暴雨', 'cultivationBonus': 1} |
| {'id': 'landslide', 'name': '山崩', 'exploreDamage': 2} |
| {'id': 'array_fault', 'name': '阵法异常'} |
| {'id': 'pulse', 'name': '灵脉波动', 'cultivationBonus': 2} |
| {'id': 'missing', 'name': 'NPC失踪', 'missingNpc': 'guide'} |
| {'id': 'evil', 'name': '邪修活动', 'exploreDamage': 1} |
| {'id': 'sect_conflict', 'name': '宗门冲突'} |

世界随行动推进游戏时间；跨日生成配置事件并保存 world_events/world_flags，反派推进和 NPC 特殊事件也存标记。第一版没有现实时间后台调度；无人行动时世界不会按现实秒数自动推进。

## 坏事件（10类）


| ID | 灾档 | 受限动作 | 处置 |
| --- | --- | --- | --- |
| deviation | 走火入魔 | cultivate,breakthrough | {'care': {'name': '请专业修士处置', 'stones': 8, 'hours': 2, 'success': 100}, 'materials': {'name': '以灵药和材料修复', 'item': 'herb', 'quantity': 2, 'hours': 1, 'success': 100}, 'self': {'name': '谨慎自行处理', 'qi': 10, 'hours': 4, 'success': 80}} |
| meridians | 经脉受损 | breakthrough | {'care': {'name': '请专业修士处置', 'stones': 8, 'hours': 2, 'success': 100}, 'materials': {'name': '以灵药和材料修复', 'item': 'herb', 'quantity': 2, 'hours': 1, 'success': 100}, 'self': {'name': '谨慎自行处理', 'qi': 10, 'hours': 4, 'success': 80}} |
| furnace | 丹炉炸裂 | craft | {'care': {'name': '请专业修士处置', 'stones': 8, 'hours': 2, 'success': 100}, 'materials': {'name': '以灵药和材料修复', 'item': 'herb', 'quantity': 2, 'hours': 1, 'success': 100}, 'self': {'name': '谨慎自行处理', 'qi': 10, 'hours': 4, 'success': 80}} |
| formation | 阵法反噬 | prepare_formation | {'care': {'name': '请专业修士处置', 'stones': 8, 'hours': 2, 'success': 100}, 'materials': {'name': '以灵药和材料修复', 'item': 'herb', 'quantity': 2, 'hours': 1, 'success': 100}, 'self': {'name': '谨慎自行处理', 'qi': 10, 'hours': 4, 'success': 80}} |
| beast_injury | 灵兽受伤 | manage_beast | {'care': {'name': '请专业修士处置', 'stones': 8, 'hours': 2, 'success': 100}, 'materials': {'name': '以灵药和材料修复', 'item': 'herb', 'quantity': 2, 'hours': 1, 'success': 100}, 'self': {'name': '谨慎自行处理', 'qi': 10, 'hours': 4, 'success': 80}} |
| artifact | 法器损坏 | fight | {'care': {'name': '请专业修士处置', 'stones': 8, 'hours': 2, 'success': 100}, 'materials': {'name': '以灵药和材料修复', 'item': 'herb', 'quantity': 2, 'hours': 1, 'success': 100}, 'self': {'name': '谨慎自行处理', 'qi': 10, 'hours': 4, 'success': 80}} |
| poison | 中毒 | cultivate | {'care': {'name': '请专业修士处置', 'stones': 8, 'hours': 2, 'success': 100}, 'materials': {'name': '以灵药和材料修复', 'item': 'herb', 'quantity': 2, 'hours': 1, 'success': 100}, 'self': {'name': '谨慎自行处理', 'qi': 10, 'hours': 4, 'success': 80}} |
| trapped | 秘境受困 | travel | {'care': {'name': '请专业修士处置', 'stones': 8, 'hours': 2, 'success': 100}, 'materials': {'name': '以灵药和材料修复', 'item': 'herb', 'quantity': 2, 'hours': 1, 'success': 100}, 'self': {'name': '谨慎自行处理', 'qi': 10, 'hours': 4, 'success': 80}} |
| ambush | 妖兽袭击 | explore | {'care': {'name': '请专业修士处置', 'stones': 8, 'hours': 2, 'success': 100}, 'materials': {'name': '以灵药和材料修复', 'item': 'herb', 'quantity': 2, 'hours': 1, 'success': 100}, 'self': {'name': '谨慎自行处理', 'qi': 10, 'hours': 4, 'success': 80}} |
| sect_accident | 宗门事故 | craft | {'care': {'name': '请专业修士处置', 'stones': 8, 'hours': 2, 'success': 100}, 'materials': {'name': '以灵药和材料修复', 'item': 'herb', 'quantity': 2, 'hours': 1, 'success': 100}, 'self': {'name': '谨慎自行处理', 'qi': 10, 'hours': 4, 'success': 80}} |

触发→未结案持续存在→限制对应行动→care/materials/self不同资源与时耗/成功率→成功结案→保留记录。重复结案拒绝。处置失败消耗资源且事件仍存在；具名灾档及随机结算持久化。

## 战斗公式与结算顺序


固定顺序：校验已学/境界/灵力/冷却 → 比较有效灵敏（同速玩家先） → 控制跳过行动 → 消耗灵力并设置冷却 → 命中 → 伤害/状态 → 灵兽 → 持续效果与持续时间 → 胜负与掉落。

```text
基础伤害 = max(1, power × strength // 100 + 3 × 境界差 − defense)
命中率 = clamp(accuracy + 2 × (agility − target_agility), 20, 100)
逃跑率 = clamp(60 + 3 × (agility − target_agility) + 技能bonus, 10, 95)
冷却可用回合 = 使用回合 + cooldown + 1
```

属性加入装备、当前功法被动和固定状态。最终伤害逐次应用宗门、妖兽、遭遇战和剑势等百分比，整数舍入，再加入杀阵固定伤害并扣护盾。控制/debuff按固定 effectChance 二次掷点；持续伤害在回合结束结算。所有随机点由保存的序列产生，并记录目的和点数。AI 可逐回合选择已有技能、丹药或撤退，禁止提交临时参数改变伤害。落败扣灵石/修为、掉一个库存物品并负伤，回到恢复地点，灾档需处理。

## 修炼、突破与出生

新角色五行灵根抽取1–5个不同元素，根数权重10/25/35/20/10；资质1–5独立按同权重抽取。角色创建后保存，不随查询、重启或改名重抽。旧存档保留原值。

```text
修为收益 = 小时 × (4 + 资质 + 功法修炼加值 + 功法等级−1
                 + 灵根契合加值2或0 + 境界序号 + 世界事件加值)
           再应用主方向/跨流派成长倍率
maxQi = 50 + 境界序号×20 + 阶段序号×5 + 功法灵力加值
突破修为需求 = 当前境界cost × (阶段序号+1)
突破成功率 = min(100, 境界基础chance + 资质×2 + 有效神识//5 + 丹品加值)
```

修炼和闭关1–72游戏小时；只能在本宗或散修坊市客舍。突破检查地点、气血满值、无异常状态、已学当前功法、驾驭境界、冷却、修为；跨大境界还检查下一境声望和对应丹药。丹药先消耗，失败损失需求修为的1/3、按境界扣血、负伤、冷却一天并留下经脉灾档；成功扣需求修为，升阶段或境界，力量+3、防御+1、气血上限+20、灵力上限+10并恢复。


| 境界 | cost | 基础chance | 进入材料 | 进入声望 |
| --- | --- | --- | --- | --- |
| 炼气 | 20 | 95 | None | 0 |
| 筑基 | 40 | 90 | foundation_pill | 5 |
| 金丹 | 60 | 85 | golden_pill | 10 |
| 元婴 | 80 | 80 | soul_pill | 15 |


## AI/Web、启动和接入

启动命令、两端同凭证配置见 README，Zeabur 发布、版本检查及旧档备份见 DEPLOY。HTTP 共号，stdio 默认是 local 独立角色。FastAPI 使用原来源/域名限制，独立请求身份，玩家没有数据库恢复权限。

## 验证和当前限制

最终验证：142 项 Python 游戏/协议测试；真实玩家循环完成到筑基与潮生秘境；浏览器完整交互和390px布局通过。容器工作流状态以本次发布结果为准。完整循环演示调用聚合命令，包含导师、任务、逐回合战斗、库存奖励、返回交付、买筑基丹、修炼、突破与高级地图/秘境。协议测试通过真实 stdio 重放演示，以及真实 Streamable HTTP 验证 Web/MCP 同状态。网页检查包含12点地图、NPC教学、移动、技能回合、改名/刷新、同号接入和390px手机布局。

当前尚未实现：组队与师徒编制、死亡转世、复杂天劫、跨岛世界、完整宗门竞争与门规执法、独立灵兽进化树、不同 NPC 的复杂日程和自由对话、玩家自建拍卖。任务分支目前为统一 report/protect 两类，剧情深度可以继续扩展。灾档处置采用三类通用方案；有持久代价和限制，未做每种事故的大型剧情。世界按游戏行动推进，未实现现实时间后台。金丹/元婴有规则，但完整成长演示目前验证到筑基及秘境；高境界专属区域与经济平衡还需扩充。保存仍重载世界集合，规模扩大需增量写入及历史/幂等缓存维护。

本地测试与推送不等于 Zeabur 已发布；应通过实际线上版本、工具列表和发布日志验证。
