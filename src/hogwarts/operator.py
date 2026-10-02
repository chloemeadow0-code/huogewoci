"""Trusted local operator CLI. Deliberately absent from the player MCP server."""
import argparse

from lorekit.support.checkpoint import manual_save, save_list, save_load

from .engine import Game


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default='data/hogwarts.db')
    parser.add_argument('action', choices=['save', 'load', 'list'])
    parser.add_argument('name', nargs='?')
    args = parser.parse_args()
    if args.action != 'list' and not args.name:
        parser.error('save/load requires a name')
    game = Game(args.db)
    try:
        if args.action == 'save':
            print(manual_save(game.db, game.sid, args.name))
        elif args.action == 'load':
            print(save_load(game.db, game.sid, args.name))
        else:
            print(save_list(game.db, game.sid))
    finally:
        game.close()


if __name__ == '__main__':
    main()
