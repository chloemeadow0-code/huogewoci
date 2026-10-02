"""Lingxi aggregate MCP tools; player commands share the Web dispatcher."""

import argparse
from mcp.server.fastmcp import FastMCP
from .engine import LOCK
from .island import IslandGame, ISLAND
from .mcp_dispatch import HELP, MCP_TOOLS, dispatch, _call_ops, manual


def create_server(db_path, identity_provider=None, **settings):
    app = FastMCP(
        "lingxi-island",
        **settings,
        instructions="你是一位灵汐島修士。仅使用13个聚合工具，整句子命令写进command。不会时relay_manual或help。系统结果是唯一事实；禁止编造招式数值。人类网页与AI共用同一角色，先读状态再行动。"
    )

    def execute(group, command="", request_id=None):
        with LOCK:
            game = IslandGame(
                db_path, **(identity_provider() if identity_provider else {})
            )
            try:
                return dispatch(game, group, command, request_id)
            finally:
                game.close()

    @app.tool()
    async def relay_manual() -> dict:
        """灵汐岛完整操作手册、地图与固定规则。无参数；先读，再选路线自主行动。"""
        return {
            "ok": True,
            "result": manual(),
            "changes": {},
            "new_events": [],
            "available_actions": [],
        }

    def register(group):
        async def bundled(command: str = "", request_id: str | None = None) -> dict:
            return await _call_ops(execute, group, command, request_id)

        app.tool(
            name=group,
            description=HELP[group]
            + " 每次返回结果、变化、新事件和可用指令。修改请求可附request_id以安全重试。",
        )(bundled)

    for group in HELP:
        register(group)

    @app.resource("xiuxian://rules")
    def rules() -> dict:
        from .engine import CONTENT

        return {"rules": CONTENT, "island": ISLAND}

    @app.prompt()
    def begin_journey() -> str:
        return "先cultivator_ops sheet、world_ops status，查看sect_ops status后选择路线。通过导师、阶段任务、青竹林实战获得资源，筑基后探索月汐湖和潮生秘境。每回合选择固定招式；保持灾档闭环。"

    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/xiuxian.db")
    args = parser.parse_args()
    game = IslandGame(args.db)
    game.close()
    create_server(args.db).run(transport="stdio")


if __name__ == "__main__":
    main()
