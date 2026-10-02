"""Added Hogwarts player engine. Reuses LoreKit DB, regions, time, memory, saves.

All extension state lives in session_meta so upstream snapshots restore it too.
One trusted local operator owns a DB; players interact only through the MCP facade.
"""
from __future__ import annotations

import copy
import json
import threading
from datetime import datetime, timedelta
from pathlib import Path

from lorekit.db import get_db, init_schema
from lorekit.narrative import region, time
from lorekit.npc.memory import add_memory, get_memories, set_core
from lorekit.support import checkpoint

from .rules import RuleError, bounded_int, can_cast, require

PACK = Path(__file__).resolve().parents[2] / 'systems' / 'hogwarts'
TOOLS = ('look', 'move', 'inspect', 'talk', 'ask', 'give', 'check_status',
         'check_schedule', 'check_inventory', 'attend_class', 'study',
         'practice_spell', 'cast_spell', 'use_item', 'read', 'search', 'sleep', 'wait')
READ_ONLY = {'look', 'inspect', 'check_status', 'check_schedule', 'check_inventory'}
LOCK = threading.RLock()


def load_pack():
    return {name: json.loads((PACK / f'{name}.json').read_text(encoding='utf-8'))
            for name in ('system', 'world', 'spells', 'courses', 'items')}


class Game:
    def __init__(self, db_path, player_key=None, player_name='新生'):
        self.player_key = player_key
        self.player_name = player_name
        self.path = str(Path(db_path).resolve())
        self.pack = load_pack()
        with LOCK:
            init_schema(self.path)
            self.db = get_db(self.path)
            rows = self.db.execute("SELECT id FROM sessions WHERE system_type='hogwarts'").fetchall()
            require(len(rows) <= 1, '一个数据库只支持一个共享校园。')
            self.sid = rows[0][0] if rows else self._bootstrap()
            self._load()
            if player_key is not None and player_key not in self.state.get('players', {}):
                self._new_player(player_key, player_name)
                self._store()
                checkpoint.create_checkpoint(self.db, self.sid)

    def _new_player(self, key, name):
        require(isinstance(key, str) and 1 <= len(key) <= 64, '非法身份。')
        require(isinstance(name, str) and 2 <= len(name) <= 24, '名字须为 2～24 字。')
        cid = self.db.execute(
            'INSERT INTO characters(session_id,name,type,region_id) VALUES (?,?,?,?)',
            (self.sid, name, 'pc', self.state['region_ids']['hospital'])).lastrowid
        record = {
            'player_id': cid,
            'player': {'name': name, 'house': 'Ravenclaw', 'year': 1,
                       'wand': '榛木／独角兽毛／十一英寸', 'stamina': 100, 'coins': 20,
                       'house_points': 0, 'learned_spells': {},
                       'inventory': {'wand': 1, 'textbook': 1, 'apple': 2}, 'known_facts': [],
                       'location': 'hospital', 'sleeping': True, 'permissions': [], 'violations': []},
            'effects': {'wand_lit': False, 'shield_until': None}, 'attendance': [],
            'knowledge': {}, 'relationships': {n: 0 for n in self.state['npc_ids']}, 'patrol_days': [],
        }
        self.state.setdefault('players', {})[key] = record
        self.progress = record

    def close(self):
        self.db.close()

    def _bootstrap(self):
        sid = self.db.execute("INSERT INTO sessions(name,setting,system_type) VALUES (?,?,?)",
                              ('雾梣学期', 'Hogwarts original campus story', 'hogwarts')).lastrowid
        self.db.commit()
        region_ids = {}
        for key, loc in self.pack['world']['locations'].items():
            result = region.create(self.db, sid, loc['name'], loc['description'])
            region_ids[key] = int(result.split(': ')[1])
        player_id = self.db.execute(
            "INSERT INTO characters(session_id,name,type,region_id) VALUES (?,?,?,?)",
            (sid, '新生', 'pc', region_ids['hospital'])).lastrowid
        npc_ids = {}
        for key, npc in self.pack['world']['npcs'].items():
            npc_ids[key] = self.db.execute(
                "INSERT INTO characters(session_id,name,type,region_id) VALUES (?,?,?,?)",
                (sid, npc['name'], 'npc', region_ids[npc['location']])).lastrowid
        self.db.commit()
        for key, nid in npc_ids.items():
            npc = self.pack['world']['npcs'][key]
            set_core(self.db, sid, nid, self_concept=f"{npc['name']}，{npc['role']}，{npc['personality']}",
                     current_goals='维护校园生活与安全', emotional_state='平静', relationships='尚不认识新生')
        self.sid = sid
        self.state = {
            'version': 1, 'region_ids': region_ids, 'player_id': player_id, 'npc_ids': npc_ids,
            'player': {'name': '新生', 'house': 'Ravenclaw', 'year': 1,
                       'wand': '榛木／独角兽毛／十一英寸', 'stamina': 100, 'coins': 20,
                       'house_points': 0, 'learned_spells': {},
                       'inventory': {'wand': 1, 'textbook': 1, 'apple': 2}, 'known_facts': [],
                       'location': 'hospital', 'sleeping': True, 'permissions': [], 'violations': []},
            'objects': {'feather': {'levitating': False, 'summoned': False},
                        'chest': {'locked': True, 'opened': False}, 'cup': {'broken': True},
                        'cauldron': {'dirty': True}, 'plant': {'watered': False}, 'dummy': {'armed': True}},
            'effects': {'wand_lit': False, 'shield_until': None}, 'attendance': [],
            'knowledge': {}, 'relationships': {key: 0 for key in npc_ids},
            'npc_inventory': {key: {} for key in npc_ids}, 'patrol_days': [],
        }
        time.set_time(self.db, sid, self.pack['world']['start_time'])
        self._store()
        checkpoint.create_checkpoint(self.db, sid)
        return sid

    def _load(self):
        row = self.db.execute("SELECT value FROM session_meta WHERE session_id=? AND key='hogwarts_state'",
                              (self.sid,)).fetchone()
        require(row is not None, '存档缺少 Hogwarts 状态。')
        self.state = json.loads(row[0])
        require(self.state['version'] == 1, '不支持该存档版本。')
        self.progress = self.state if self.player_key is None else self.state.get('players', {}).get(self.player_key)

    @property
    def player_id(self):
        return self.progress['player_id']

    @property
    def player(self):
        return self.progress['player']

    @property
    def now(self):
        return datetime.fromisoformat(time._get_narrative_time(self.db, self.sid))

    def _store(self):
        self.db.execute(
            "INSERT INTO session_meta(session_id,key,value) VALUES (?,'hogwarts_state',?) "
            "ON CONFLICT(session_id,key) DO UPDATE SET value=excluded.value",
            (self.sid, json.dumps(self.state, ensure_ascii=False)))
        for record in [self.state, *self.state.get('players', {}).values()]:
            self.db.execute('UPDATE characters SET region_id=? WHERE id=?',
                            (self.state['region_ids'][record['player']['location']], record['player_id']))
        self.db.commit()

    def _resolve(self, table, value):
        require(isinstance(value, str), '名称必须是字符串。')
        entries = self.pack[table] if table != 'locations' and table != 'npcs' else self.pack['world'][table]
        for key, entry in entries.items():
            if value in (key, entry['name']):
                return key
        raise RuleError('找不到这个名称。')

    def _npc_location(self, key):
        if key == 'professor' and self.now.weekday() < 5:
            for course in self.pack['courses'].values():
                if course['hour'] <= self.now.hour < course['hour'] + 1:
                    return course['location']
        return self.pack['world']['npcs'][key]['location']

    def _npc(self, value):
        key = self._resolve('npcs', value)
        require(self._npc_location(key) == self.player['location'], '该人物不在这里。')
        return key

    def _remember(self, key, content, importance=0.5, player_id=None):
        add_memory(self.db, self.sid, self.state['npc_ids'][key], content, importance,
                   'experience', [player_id or self.player_id], self.now.isoformat(timespec='minutes'))

    def _learn_fact(self, key):
        if key not in self.player['known_facts']:
            self.player['known_facts'].append(key)
        return self.pack['world']['facts'][key]

    def _advance(self, minutes):
        before = self.now
        time.advance(self.db, self.sid, minutes, 'minutes')
        after = self.now
        # Find every curfew interval crossed, including wait/sleep spanning midnight.
        cursor = before.replace(hour=0, minute=0) - timedelta(days=1)
        while cursor <= after:
            night_start = cursor.replace(hour=22)
            night_end = night_start + timedelta(hours=8)
            day = cursor.date().isoformat()
            for record in [self.state, *self.state.get('players', {}).values()]:
                player = record['player']
                exposed = player['location'] != 'hospital' and before < night_end and after >= night_start
                if not exposed:
                    continue
                if day not in record['patrol_days']:
                    event = {'kind': 'curfew', 'time': max(before, night_start).isoformat(timespec='minutes'),
                             'location': player['location'], 'witness': '奥伦·石栎',
                             'penalty': self.pack['system']['rules']['night_penalty']}
                    player['violations'].append(event)
                    player['house_points'] -= event['penalty']
                    record['patrol_days'].append(day)
                    self._remember('caretaker', f"巡查抓到{player['name']}夜游：{event['location']}，扣五分。",
                                   0.9, record['player_id'])
                    notice = '奥伦·石栎发现你夜游，扣五分并记录违规，送回校医院休息。'
                else:
                    notice = '奥伦·石栎再次送你回校医院，同一夜不重复扣分。'
                if record['player_id'] == self.player_id:
                    self._notices.append(notice)
                player['location'] = 'hospital'
            cursor += timedelta(days=1)
        for record in [self.state, *self.state.get('players', {}).values()]:
            expiry = record['effects']['shield_until']
            if expiry and self.now >= datetime.fromisoformat(expiry):
                record['effects']['shield_until'] = None
        for key, nid in self.state['npc_ids'].items():
            self.db.execute('UPDATE characters SET region_id=? WHERE id=?',
                            (self.state['region_ids'][self._npc_location(key)], nid))
        self.db.commit()

    def call(self, tool, **kwargs):
        with LOCK:
            self._load()
            self._notices = []
            require(tool in TOOLS, '玩家工具未开放。')
            before = checkpoint.snapshot_session(self.db, self.sid)
            cursor = checkpoint._get_cursor(self.db, self.sid)
            try:
                result = getattr(self, tool)(**kwargs)
                if tool not in READ_ONLY:
                    self._store()
                    checkpoint.create_checkpoint(self.db, self.sid)
                return {'ok': True, 'time': self.now.isoformat(timespec='minutes'),
                        'result': result, 'notices': self._notices}
            except (RuleError, TypeError) as exc:
                # Upstream APIs commit independently. Restore the full pre-action snapshot
                # to keep failed actions (including NPC memories and clock) atomic.
                self.db.rollback()
                checkpoint.restore_snapshot(self.db, self.sid, before)
                if all(x is not None for x in cursor):
                    checkpoint._set_cursor(self.db, self.sid, *cursor)
                    self.db.commit()
                self._load()
                return {'ok': False, 'error': str(exc)}
            except Exception:
                self.db.rollback()
                checkpoint.restore_snapshot(self.db, self.sid, before)
                if all(x is not None for x in cursor):
                    checkpoint._set_cursor(self.db, self.sid, *cursor)
                    self.db.commit()
                self._load()
                raise

    def _awake(self):
        require(not self.player['sleeping'], '你还在睡觉；使用 sleep(hours=0) 起床。')

    def look(self):
        key = self.player['location']
        loc = self.pack['world']['locations'][key]
        return {'location': key, 'name': loc['name'], 'description': loc['description'],
                'exits': [{'id': x, 'name': self.pack['world']['locations'][x]['name']} for x in loc['exits']],
                'npcs': [{'id': n, 'name': p['name'], 'role': p['role']}
                         for n, p in self.pack['world']['npcs'].items() if self._npc_location(n) == key],
                'objects': loc['objects']}

    def move(self, destination: str):
        self._awake()
        key = self._resolve('locations', destination)
        require(key in self.pack['world']['locations'][self.player['location']]['exits'], '地点不相连。')
        if key == 'restricted':
            require('restricted' in self.player['permissions'], '缺少禁书区许可。')
        require(self.player['stamina'] >= 1, '体力不足，先休息。')
        self.player['stamina'] -= 1
        self.player['location'] = key
        self._advance(self.pack['system']['rules']['movement_minutes'])
        return self.look()

    def inspect(self, target: str):
        if target in self.look()['objects']:
            return {'id': target, 'state': copy.deepcopy(self.state['objects'][target])}
        for npc in self.look()['npcs']:
            if target in (npc['id'], npc['name']):
                return npc
        key = self._resolve('items', target)
        require(self.player['inventory'].get(key, 0) > 0, '物品不可见。')
        item = self.pack['items'][key]
        return {'id': key, 'name': item['name'], 'description': item['description']}

    def talk(self, npc: str, message: str):
        self._awake()
        require(isinstance(message, str) and 0 < len(message) <= 1000, '对话长度须为 1～1000 字。')
        key = self._npc(npc)
        memories = [m for m in get_memories(self.db, self.state['npc_ids'][key], self.sid, limit=1000)
                    if self.player_id in json.loads(m['entities'])]
        greeting = '我记得你。' if memories else '你好，新生。'
        caught = any('巡查抓到' in m['content'] for m in memories)
        if caught and key == 'caretaker':
            greeting = '你的夜游已在记录中，请遵守宵禁。'
        self._remember(key, f'新生说：{message}')
        self.progress['relationships'][key] += 1
        facts = [self._learn_fact(f) for f in self.pack['world']['npcs'][key]['facts']]
        reply = greeting + self.pack['world']['npcs'][key]['public_reply']
        self._advance(5)
        return {'npc': self.pack['world']['npcs'][key]['name'], 'reply': reply, 'learned_facts': facts}

    def ask(self, npc: str, topic: str):
        self._awake()
        key = self._npc(npc)
        require(isinstance(topic, str) and 0 < len(topic) <= 1000, '话题长度须为 1～1000 字。')
        if key == 'professor' and topic in ('permission', '禁书区许可'):
            require(self.progress['knowledge'].get('charms', 0) >= 1, '先完成一堂魔咒课。')
            if 'restricted' not in self.player['permissions']:
                self.player['permissions'].append('restricted')
            self._remember(key, '批准新生在禁书区阅读学习。')
            self._advance(5)
            return {'reply': '给你一张禁书区学习许可。'}
        if key == 'merchant' and topic in ('buy tonic', '购买药剂'):
            require(self.player['coins'] >= 5, '金币不足。')
            self.player['coins'] -= 5
            self.player['inventory']['tonic'] = self.player['inventory'].get('tonic', 0) + 1
            self._remember(key, '新生以五枚金币购买恢复药剂。')
            self._advance(5)
            return {'reply': '交易完成。', 'item': 'tonic', 'paid': 5}
        return self.talk(key, topic)

    def give(self, npc: str, item: str, quantity: int = 1):
        self._awake()
        key = self._npc(npc)
        item = self._resolve('items', item)
        bounded_int(quantity, 1, 99)
        require(item != 'wand', '不能赠送唯一的魔杖。')
        require(self.player['inventory'].get(item, 0) >= quantity, '背包物品不足。')
        self.player['inventory'][item] -= quantity
        stock = self.state['npc_inventory'][key]
        stock[item] = stock.get(item, 0) + quantity
        self.progress['relationships'][key] += quantity
        self._remember(key, f'新生赠送了 {quantity} 个 {item}。')
        self._advance(5)
        return {'reply': '谢谢，我会记得这份礼物。'}

    def check_status(self):
        result = copy.deepcopy(self.player)
        result['known_facts'] = [self.pack['world']['facts'][f] for f in result['known_facts']]
        result['effects'] = copy.deepcopy(self.progress['effects'])
        return result

    def check_schedule(self):
        date = self.now.date().isoformat()
        return {'date': date, 'weekday': self.now.weekday(), 'classes': [
            {'id': key, 'name': c['name'], 'location': c['location'], 'teacher': c['teacher'],
             'start': f"{date}T{c['hour']:02d}:00", 'duration_minutes': c['duration']}
            for key, c in self.pack['courses'].items()] if self.now.weekday() < 5 else [],
            'curfew': '22:00–06:00'}

    def check_inventory(self):
        return [{'id': key, 'name': self.pack['items'][key]['name'], 'quantity': count}
                for key, count in self.player['inventory'].items() if count > 0]

    def attend_class(self, course: str):
        self._awake()
        key = self._resolve('courses', course)
        c = self.pack['courses'][key]
        require(self.player['location'] == c['location'], '请先到上课地点。')
        start = self.now.replace(hour=c['hour'], minute=0)
        require(self.now.weekday() < 5 and start <= self.now <= start + timedelta(minutes=15), '未在开课后十五分钟内签到。')
        token = f'{self.now.date()}:{key}'
        require(token not in self.progress['attendance'], '今天已经上过这门课。')
        require(self.player['stamina'] >= 8, '体力不足。')
        self.player['stamina'] -= 8
        self.progress['attendance'].append(token)
        self.progress['knowledge'][key] = self.progress['knowledge'].get(key, 0) + 1
        for spell in c['spells']:
            self.player['learned_spells'].setdefault(spell, 1)
        self.player['house_points'] += 2
        self._remember(c['teacher'], f'新生完成了{c["name"]}，学会：{c["spells"]}。')
        end = start + timedelta(minutes=c['duration'])
        self._advance(int((end - self.now).total_seconds() // 60))
        return {'completed': c['name'], 'learned_spells': c['spells'], 'house_points_awarded': 2}

    def study(self, spell: str):
        self._awake()
        key = self._resolve('spells', spell)
        require(self.player['inventory'].get('textbook', 0) > 0, '需要练习册。')
        require(self.player['location'] in ('library', 'restricted'), '请到图书馆学习。')
        require(key in self.pack['items']['textbook']['spells'], '课本没有此咒语。')
        require(key not in self.player['learned_spells'], '已经学过，使用 practice_spell 练习。')
        require(self.player['stamina'] >= 10, '体力不足。')
        self.player['stamina'] -= 10
        self.player['learned_spells'][key] = 1
        self._advance(30)
        return {'learned': key, 'proficiency': 1}

    def practice_spell(self, spell: str):
        self._awake()
        key = self._resolve('spells', spell)
        require(key in self.player['learned_spells'], '你尚未学会这个魔咒。')
        require(self.player['location'] in ('library', 'pitch', 'greenhouse', 'potions'), '这里不适合练习。')
        require(self.player['inventory'].get('wand', 0) > 0, '练习需要魔杖。')
        require(self.player['stamina'] >= 5, '体力不足。')
        require(self.player['learned_spells'][key] < 5, '熟练度已达到上限。')
        self.player['stamina'] -= 5
        self.player['learned_spells'][key] += 1
        self._advance(15)
        return {'spell': key, 'proficiency': self.player['learned_spells'][key]}

    def cast_spell(self, spell: str, target: str):
        self._awake()
        key = self._resolve('spells', spell)
        spec = self.pack['spells'][key]
        success = can_cast(self.player, key, spec)
        require(target in spec['targets'], '这个魔咒不支持该目标。')
        require(target in ('wand', 'self') or target in self.look()['objects'], '目标不在这里。')
        self.player['stamina'] -= spec['cost']
        if success:
            effect = spec['effect']
            if effect == 'light_on':
                self.progress['effects']['wand_lit'] = True
            elif effect == 'light_off':
                self.progress['effects']['wand_lit'] = False
            elif effect == 'shield':
                self.progress['effects']['shield_until'] = (self.now + timedelta(minutes=10)).isoformat(timespec='minutes')
            else:
                field, value = {'levitate': ('levitating', True), 'summon': ('summoned', True),
                                'unlock': ('locked', False), 'repair': ('broken', False),
                                'clean': ('dirty', False), 'water': ('watered', True),
                                'disarm': ('armed', False)}[effect]
                self.state['objects'][target][field] = value
        self._advance(2)
        return {'spell': key, 'target': target, 'success': success, 'cost': spec['cost'],
                'effect': spec['effect'] if success else '熟练度不足，魔咒没有生效。'}

    def use_item(self, item: str):
        self._awake()
        key = self._resolve('items', item)
        require(self.player['inventory'].get(key, 0) > 0, '没有这个物品。')
        spec = self.pack['items'][key]
        require('restore' in spec, '此物品不能这样使用。')
        self.player['inventory'][key] -= 1
        self.player['stamina'] = min(100, self.player['stamina'] + spec['restore'])
        self._advance(2)
        return {'used': key, 'stamina': self.player['stamina']}

    def read(self, item: str):
        self._awake()
        key = self._resolve('items', item)
        available = self.player['inventory'].get(key, 0) > 0 or (key == 'library_book' and self.player['location'] == 'library')
        require(available, '这里没有这份读物。')
        spec = self.pack['items'][key]
        require('spells' in spec or 'fact' in spec, '这不是读物。')
        result = {'description': spec['description']}
        if 'spells' in spec:
            result['chapters'] = [{'id': s, 'name': self.pack['spells'][s]['name']} for s in spec['spells']]
            result['hint'] = '阅读提供目录；study 或上课才能学会魔咒。'
        if 'fact' in spec:
            result['learned_fact'] = self._learn_fact(spec['fact'])
        self._advance(10)
        return result

    def search(self, target: str):
        self._awake()
        require(target in ('shelves', 'chest'), '只能搜索 shelves 或 chest。')
        require(self.player['location'] == 'library', '这里没有这个搜索目标。')
        if target == 'chest':
            require(not self.state['objects']['chest']['locked'], '练习箱还锁着。')
            self.state['objects']['chest']['opened'] = True
            result = {'discovery': self._learn_fact('hidden_label')}
        else:
            result = {'books': [{'id': 'library_book', 'name': self.pack['items']['library_book']['name']}]}
        self._advance(10)
        return result

    def sleep(self, hours: int = 8):
        bounded_int(hours, 0, 12)
        require(self.player['location'] == 'hospital', '第一版只开放校医院休息床位。')
        self.player['sleeping'] = False
        if hours:
            self._advance(hours * 60)
            self.player['stamina'] = min(100, self.player['stamina'] + hours * 12)
        return {'awake': True, 'stamina': self.player['stamina']}

    def wait(self, minutes: int):
        self._awake()
        bounded_int(minutes, 1, 720)
        self._advance(minutes)
        return {'waited_minutes': minutes, 'location': self.player['location']}
