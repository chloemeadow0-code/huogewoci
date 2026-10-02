# 灵汐岛架构与改造记录

## 底座和调用关系

主项目是 `chloemeadow0-code/huogewoci` 中已实现的青云问道，名称统一为灵汐岛，继续保留 Git 历史、凭证和修行进度。没有将主项目换成另一个仓库。

检查 allotment-relay 的 MCP 入口/dispatch、FastAPI、SQLite、v1 auth/idempotency、world/events/progress/npc/tale/story 和模块前端的调用关系；本地源码索引扫描 350 个 Python/JS/CSS/HTML 文件，重点阅读相关框架和玩法闭环。借鉴并适配聚合工具、SQLite 重试、请求幂等及前端请求结构，保留 MIT 许可在 `third_party/allotment-relay/LICENSE`。没有声称逐行审读 13 万行源代码。

潮汐岛的农田、捕鱼、婚姻、剧场等业务没有导入本仓库，因此此次不存在“先复制再删除”这些模块。主项目之前的 Hogwarts 专属代码已在早先修仙改造中替换；本次复用现有修仙规则，避免重新实现战斗和五路线。

```text
HTTP 凭证 / MCP 请求
  → auth 身份边界
  → 13 个聚合工具 / v1 command
  → mcp_dispatch 解析固定子命令、SQLite 锁重试
  → IslandGame.call BEGIN IMMEDIATE
  → 幂等查验、灾档限制、现有 Game/RouteMechanics 规则
  → 世界/任务/履历增量及缓存一起写入独立表
  → commit → result/changes/new_events/available_actions
```

前端 `api/store → app → map/hud/scenes/place/ui/modal` 使用同一个 v1 路由；5 秒刷新。真实 MCP 支持 stdio 和 Streamable HTTP，资源保留 `xiuxian://rules`、提示 `begin_journey`。玩家工具不会注册快照/加载/管理员功能。

## 文件变更

| 文件 | 作用 |
|---|---|
| src/xiuxian/engine.py | 抽取 new_player 与可覆盖的读取接口，保留固定战斗/成长规则 |
| src/xiuxian/db.py | 独立表、WAL、旧 JSON 导入及表行装载保存 |
| src/xiuxian/island.py | 12 地点、NPC、阶段任务、灾档、物品履历、拍卖、幂等事务 |
| src/xiuxian/mcp_dispatch.py | 13 聚合工具、严格参数解析、help、命令提示与锁重试 |
| src/xiuxian/server.py | MCP 注册、共享 dispatcher、资源及 prompt |
| src/xiuxian/auth.py | api_keys 表迁移及原凭证兼容 |
| src/xiuxian/http_app.py | FastAPI 入口、v1 API、两端共享权限与角色 |
| src/xiuxian/operator.py | 新独立表快照恢复，涵盖拍卖和幂等缓存 |
| src/xiuxian/island_demo.py | 仅玩家命令的完整循环演示 |
| web/index.html/style.css/app.js/manual.html | 灵汐岛页面、交互和新版人类手册 |
| web/api.js/store.js/map.js/hud.js | 请求重试、同号状态、地图、角色面板 |
| web/scenes/place.js、web/ui/*、web/catalog.js | 地点功能、人物、任务、斗法、物品、炼制和弹窗 |
| systems/xiuxian/island.json | 12 地点、18 NPC、6 敌对人物、30 阶段任务、13 事件、10 灾档 |
| systems/xiuxian/content.json | 复用宗门、境界、配方、技能，补全八类技能和功法类型 |
| systems/xiuxian/requirements-deploy.txt | FastAPI 与现有 MCP 依赖锁定 |
| tests/xiuxian/test_island.py、test_protocol.py、test_game.py | 新模型和完整协议/循环测试，适配工具注册 |
| Dockerfile、NOTICE、third_party/*、.github/workflows/xiuxian-deploy.yml | 容器许可证及持续检查 |
| README.md、DEPLOY.md、ROUTES.md、LINGXI.md | 当前接入、规则与部署文档 |

## 数据状态

在线入口使用 `IslandGame + Store`，核心字段、背包、装备、技能、关系、任务和事件分表。旧 `Game` 的 LoreKit JSON 保存接口仍供既有规则测试与旧版兼容使用，**在线入口不使用它存储全世界**。少量灵活元数据、战斗结构、任务配置和历史结果保留 JSON 列，备份快照也用 JSON；没有把整个在线状态塞回一个 JSON 字段。

迁移仅首次执行，旧 JSON 保持原样作为恢复参考。灵根和资质不重新抽取；改名不重置信誉、关系或进度。身份不接受用户参数覆写。事务将奖励、资源扣除、随机序列与幂等响应共同提交。

当前保存方式每次装载和保存共享世界的玩家集合，适合单副本小规模第一版。大量玩家和长历史需要增量 SQL 更新、历史分页及缓存清理，不应宣称已达到大规模在线性能。

完整表、命令、内容、公式、验证及缺项见 [LINGXI.md](LINGXI.md)。
