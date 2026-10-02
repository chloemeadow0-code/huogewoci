"""Repeatable demo using exactly the same player actions as MCP."""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from .engine import Game


def run_demo(db_path):
    game = Game(db_path)
    transcript = []

    def step(tool, **args):
        response = game.call(tool, **args)
        assert response['ok'], response
        transcript.append({'tool': tool, 'arguments': args, 'response': response})
        return response

    try:
        step('sleep', hours=0)
        step('check_schedule')
        step('move', destination='hall')
        step('talk', npc='student', message='今天是我第一天上课，有什么建议？')
        step('move', destination='library')
        # 06:25 -> 09:00, derived from narrative clock rather than an admin time jump.
        step('wait', minutes=155)
        step('attend_class', course='charms')
        step('cast_spell', spell='lumos', target='wand')
        step('talk', npc='professor', message='我已经能让魔杖发光了！')
        step('move', destination='hall')
        step('move', destination='hospital')
        # Rest on the allowed bed, then leave shortly before curfew.
        step('sleep', hours=11)
        step('wait', minutes=8)
        step('move', destination='hall')
        step('move', destination='lake')
        step('wait', minutes=10)
        status = step('check_status')['result']
        assert status['violations'] and status['house_points'] == -3
        assert status['location'] == 'hospital'
        assert 'lumos' in status['learned_spells']
        return transcript
    finally:
        game.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', help='Save the player-visible JSON transcript')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='hogwarts-demo-') as tmp:
        transcript = run_demo(Path(tmp) / 'demo.db')
    text = json.dumps(transcript, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(text, encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
