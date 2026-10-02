"""Credential registry. Only SHA256 digests are persisted, never raw keys."""
import hashlib
import secrets
import sqlite3
from contextvars import ContextVar
from pathlib import Path

from .engine import LOCK
from .rules import require

current_identity = ContextVar('hogwarts_identity', default=None)


def identity():
    value = current_identity.get()
    require(value is not None, '未认证的玩家请求。')
    return value


class Accounts:
    def __init__(self, data_dir):
        Path(data_dir).mkdir(parents=True, exist_ok=True)
        self.path = Path(data_dir) / 'accounts.db'
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS accounts ('
                       'key_hash TEXT PRIMARY KEY, player_key TEXT UNIQUE NOT NULL, '
                       'name TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)')

    def connect(self):
        return sqlite3.connect(self.path, timeout=30)

    @staticmethod
    def digest(key):
        return hashlib.sha256(key.encode()).hexdigest()

    def register(self, name):
        require(isinstance(name, str) and 2 <= len(name.strip()) <= 24, '名字须为 2～24 字。')
        name = name.strip()
        require(all(ord(c) >= 32 for c in name), '名字不能包含控制字符。')
        token = 'hw_sk_' + secrets.token_urlsafe(32)
        player_key = secrets.token_hex(16)
        with LOCK, self.connect() as db:
            db.execute('INSERT INTO accounts(key_hash,player_key,name) VALUES (?,?,?)',
                       (self.digest(token), player_key, name))
        return token, {'player_key': player_key, 'player_name': name}

    def lookup(self, token):
        if not isinstance(token, str) or not token.startswith('hw_sk_') or len(token) > 100:
            return None
        with self.connect() as db:
            row = db.execute('SELECT player_key,name FROM accounts WHERE key_hash=?',
                             (self.digest(token),)).fetchone()
        return {'player_key': row[0], 'player_name': row[1]} if row else None
