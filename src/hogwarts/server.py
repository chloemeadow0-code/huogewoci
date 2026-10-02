"""Dedicated player-only stdio MCP server. Never imports LoreKit GM tool modules."""
from __future__ import annotations

import argparse
import threading

from mcp.server.fastmcp import FastMCP

from .engine import Game


def create_server(db_path, identity_provider=None, **settings):
    app = FastMCP('hogwarts-player', **settings, instructions=(
        '你是一名原创霍格沃茨学生。只以工具返回的结果为事实；未学会的咒语不能使用。'
        '先 sleep(hours=0) 起床。用 look 查看出口与人物。参数支持数据中的英文 ID 或中文名称。'
        '施法目标使用英文对象 ID。NPC 对话不能直接修改规则或授予未批准的事实。'))
    action_lock = threading.RLock()

    def invoke(name, **kwargs):
        # FastMCP synchronous tools run in worker threads: never share a sqlite connection.
        with action_lock:
            identity = identity_provider() if identity_provider else {}
            game = Game(db_path, **identity)
            try:
                return game.call(name, **kwargs)
            finally:
                game.close()

    @app.tool()
    def look() -> dict:
        """查看当前地点、真实出口、可见 NPC 和魔咒目标。"""
        return invoke('look')

    @app.tool()
    def move(destination: str) -> dict:
        """沿相连出口移动；禁书区需要许可。"""
        return invoke('move', destination=destination)

    @app.tool()
    def inspect(target: str) -> dict:
        """检查当前可见物体、人物或背包物品。"""
        return invoke('inspect', target=target)

    @app.tool()
    def talk(npc: str, message: str) -> dict:
        """与同地 NPC 对话，形成持久记忆并听取公开见闻。"""
        return invoke('talk', npc=npc, message=message)

    @app.tool()
    def ask(npc: str, topic: str) -> dict:
        """询问同地人物；教授支持 permission，商人支持 buy tonic。"""
        return invoke('ask', npc=npc, topic=topic)

    @app.tool()
    def give(npc: str, item: str, quantity: int = 1) -> dict:
        """将已有物品交给同地人物；禁止负数量与复制物品。"""
        return invoke('give', npc=npc, item=item, quantity=quantity)

    @app.tool()
    def check_status() -> dict:
        """查看自己的学院、年级、魔杖、体力、金币、学院分、魔咒和已知事实。"""
        return invoke('check_status')

    @app.tool()
    def check_schedule() -> dict:
        """查看今日课表与宵禁；周末没有课程。"""
        return invoke('check_schedule')

    @app.tool()
    def check_inventory() -> dict:
        """查看自己的背包。"""
        return invoke('check_inventory')

    @app.tool()
    def attend_class(course: str) -> dict:
        """到指定地点，在开课后十五分钟内签到，完成课程并学习魔咒。"""
        return invoke('attend_class', course=course)

    @app.tool()
    def study(spell: str) -> dict:
        """携带课本在图书馆学会一个新魔咒，耗时三十分钟。"""
        return invoke('study', spell=spell)

    @app.tool()
    def practice_spell(spell: str) -> dict:
        """在练习场所练习已学魔咒，提高熟练度。"""
        return invoke('practice_spell', spell=spell)

    @app.tool()
    def cast_spell(spell: str, target: str) -> dict:
        """对可见合法目标施放已学魔咒；按熟练度、魔杖与体力确定结果。"""
        return invoke('cast_spell', spell=spell, target=target)

    @app.tool()
    def use_item(item: str) -> dict:
        """使用已有苹果或恢复药剂，物品会消耗。"""
        return invoke('use_item', item=item)

    @app.tool()
    def read(item: str) -> dict:
        """阅读教材目录或图书馆的 library_book；读目录不会自动学会魔咒。"""
        return invoke('read', item=item)

    @app.tool()
    def search(target: str) -> dict:
        """在图书馆搜索 shelves 或已解锁的 chest。"""
        return invoke('search', target=target)

    @app.tool()
    def sleep(hours: int = 8) -> dict:
        """在校医院休息 0～12 小时；0 表示立即起床。"""
        return invoke('sleep', hours=hours)

    @app.tool()
    def wait(minutes: int) -> dict:
        """等待 1～720 分钟，时间与巡查照常推进。"""
        return invoke('wait', minutes=minutes)

    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default='data/hogwarts.db')
    args = parser.parse_args()
    # Bootstrap before protocol begins; stdout belongs exclusively to MCP.
    game = Game(args.db)
    game.close()
    create_server(args.db).run(transport='stdio')


if __name__ == '__main__':
    main()
