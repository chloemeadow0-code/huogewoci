"""Central, deterministic combat formulas and input validation."""


class RuleError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise RuleError(message)


def bounded_int(value, minimum, maximum):
    require(
        type(value) is int and minimum <= value <= maximum,
        f"数值必须为 {minimum}～{maximum} 的整数",
    )
    return value


def damage(power, strength, defense, realm_delta=0):
    return max(1, power * strength // 100 + realm_delta * 3 - defense)


def hit_chance(accuracy, agility, target_agility):
    return max(20, min(100, accuracy + (agility - target_agility) * 2))


def escape_chance(agility, target_agility, bonus=0):
    return max(10, min(95, 60 + (agility - target_agility) * 3 + bonus))
