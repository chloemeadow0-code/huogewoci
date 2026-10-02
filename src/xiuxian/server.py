"""Player-only MCP facade; no GM mutation tools."""

import argparse
from mcp.server.fastmcp import FastMCP
from .engine import Game, LOCK, CONTENT


def create_server(db_path, identity_provider=None, **settings):
    app = FastMCP(
        "qingyun-player",
        **settings,
        instructions="你是一名修士。先 get_self/get_world；新角色先choose_route选择五条路线之一，再自主选择行动。只有工具结果是事实；只传技能ID，禁止编造数值。fight 开战，use_skill/use_item/retreat 逐回合行动。"
    )

    def invoke(tool_name, **kwargs):
        with LOCK:
            game = Game(db_path, **(identity_provider() if identity_provider else {}))
            try:
                return game.call(tool_name, **kwargs)
            finally:
                game.close()

    @app.tool()
    def get_self() -> dict:
        """读取个人状态、修为、招式、装备和战斗。"""
        return invoke("get_self")

    @app.tool()
    def get_world() -> dict:
        """读取附近地点、出口、NPC、敌人、任务、商店、世界事件和秘境周期。"""
        return invoke("get_world")

    @app.tool()
    def cultivate(method: str = "basic_meditation", duration: int = 1) -> dict:
        """使用已学功法修炼1至72小时，由系统计算收益。"""
        return invoke("cultivate", method=method, duration=duration)

    @app.tool()
    def travel(destination: str, node: str | None = None) -> dict:
        """沿出口移动；可指定当前区域配置中的节点。筑基可入秘境，每周期一次。"""
        return invoke("travel", destination=destination, node=node)

    @app.tool()
    def explore() -> dict:
        """系统随机探索，事件与随机数进入历史；秘境节点每周期只能探索一次。"""
        return invoke("explore")

    @app.tool()
    def talk(npc: str, topic: str = "greeting", item: str | None = None) -> dict:
        """固定选项 greeting/quest/teach/rumor/gift/help/insult/spar；不接受自由文本效果。"""
        return invoke("talk", npc=npc, topic=topic, item=item)

    @app.tool()
    def fight(target: str) -> dict:
        """与同地敌人开启战斗，之后逐回合决策。"""
        return invoke("fight", target=target)

    @app.tool()
    def use_skill(skill: str) -> dict:
        """选择已学技能ID，由系统决定先后手、命中、伤害和效果。"""
        return invoke("use_skill", skill=skill)

    @app.tool()
    def use_item(item: str) -> dict:
        """使用回气丹、阅读功法，或装备已有法器。战斗中只能用丹药。"""
        return invoke("use_item", item=item)

    @app.tool()
    def craft(recipe: str, amount: int = 1) -> dict:
        """在宗门按固定配方炼丹炼器，amount为1至20。"""
        return invoke("craft", recipe=recipe, amount=amount)

    @app.tool()
    def trade(item: str, quantity: int = 1, side: str = "buy") -> dict:
        """在宗门商店或小镇按配置固定价格买卖，quantity为1至100。"""
        return invoke("trade", item=item, quantity=quantity, side=side)

    @app.tool()
    def accept_quest(quest: str) -> dict:
        """在发布地领取机器可验证任务。"""
        return invoke("accept_quest", quest=quest)

    @app.tool()
    def submit_quest(quest: str) -> dict:
        """按库存、击杀或探索记录验证任务，只领取一次奖励。"""
        return invoke("submit_quest", quest=quest)

    @app.tool()
    def breakthrough() -> dict:
        """根据修为、境界、资源、状态计算突破，失败会受伤并冷却。"""
        return invoke("breakthrough")

    @app.tool()
    def retreat(duration: int = 1) -> dict:
        """宗门闭关疗养1至72小时；战斗中尝试撤退，八小时可治重伤。"""
        return invoke("retreat", duration=duration)

    @app.tool()
    def inspect_history(limit: int = 20) -> dict:
        """读取最近1至100条个人经历及系统随机记录。"""
        return invoke("inspect_history", limit=limit)

    @app.tool()
    def choose_route(route: str) -> dict:
        """一次性选择qingxiao/xuanheng/danxia/fuyao/rogue；选择前inspect_route查背景和规则。"""
        return invoke("choose_route", route=route)

    @app.tool()
    def inspect_route() -> dict:
        """查看五条路线完整背景、固定加成负面、特殊机制与自己的信誉门规。"""
        return invoke("inspect_route")

    @app.tool()
    def learn_technique(technique: str) -> dict:
        """宗门或私人传承学功法；主方向宗门2个散修4个，跨流派成长减速。"""
        return invoke("learn_technique", technique=technique)

    @app.tool()
    def prepare_formation(formation: str) -> dict:
        """玄衡阵门预置ward/snare/gather/kill；非遭遇战生效，每战仅一个，消耗材料。"""
        return invoke("prepare_formation", formation=formation)

    @app.tool()
    def manage_beast(
        action: str, beast: str | None = None, stance: str = "assist"
    ) -> dict:
        """灵兽contract/feed/heal/stance/release/abuse；重伤强制出战会失忠，release需登记。"""
        return invoke("manage_beast", action=action, beast=beast, stance=stance)

    @app.tool()
    def rename(name: str) -> dict:
        """修改自己的道号为2至24字；保留凭证与全部进度，不消耗游戏时间。"""
        return invoke("rename", name=name)

    @app.tool()
    def track(target: str) -> dict:
        """野外追踪；伏妖门成功率加20，追踪目标击杀有额外材料。"""
        return invoke("track", target=target)

    @app.resource("xiuxian://rules")
    def rules() -> dict:
        """公开规则与固定内容目录，不包含任何玩家凭证或私有存档。"""
        return CONTENT

    @app.prompt()
    def begin_journey() -> str:
        return "先调用 get_self、get_world、inspect_route，再choose_route确认修行路线。选择自己的成长路线；接任务、修炼、下山探索。fight 只开战，每回合读取状态选择招式。先炼气圆满，购买筑基丹，筑基后等秘境开放。"

    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/xiuxian.db")
    args = parser.parse_args()
    game = Game(args.db)
    game.close()
    create_server(args.db).run(transport="stdio")


if __name__ == "__main__":
    main()
