"""Deterministic mechanics. No narrator or LLM can mutate authoritative state."""


class RuleError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise RuleError(message)


def bounded_int(value, minimum, maximum):
    require(type(value) is int and minimum <= value <= maximum,
            f"数值必须为 {minimum}～{maximum} 的整数。")
    return value


def spell_score(proficiency, stamina, affinity=2):
    return proficiency * 2 + stamina // 20 + affinity


def can_cast(player, spell_id, spell):
    require(spell_id in player['learned_spells'], '你尚未学会这个魔咒。')
    require(player['inventory'].get('wand', 0) > 0, '施法需要随身携带魔杖。')
    require(player['stamina'] >= spell['cost'], '体力不足。')
    return spell_score(player['learned_spells'][spell_id], player['stamina']) >= spell['difficulty']
