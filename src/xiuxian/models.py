"""Central state contracts; runtime invariants are enforced in the engine."""

from typing import TypedDict, NotRequired


class StatusEffect(TypedDict):
    type: str
    value: int
    duration: int
    source: str


class Player(TypedDict):
    id: str
    name: str
    realm: str
    stage: int
    cultivation: int
    hp: int
    qi: int
    spirit: int
    strength: int
    agility: int
    defense: int
    aptitude: int
    sect: str
    location: str
    inventory: dict[str, int]
    equipment: dict[str, str | None]
    techniques: list[str]
    skills: list[str]
    relationships: dict
    statusEffects: list[StatusEffect]
    max_hp: int
    maxQi: int
    method: str
    root: str
    rootElements: list[str]
    stones: int
    reputation: int
    quests: dict[str, str]
    battle: dict | None
    cooldownUntil: int
    history: list[dict]
    createdAt: str


class Technique(TypedDict):
    name: str
    type: str
    requiredRealm: int
    compatibleRoots: list[str]
    cultivationBonus: int
    qiBonus: int
    passiveEffects: dict[str, int]
    maxLevel: int


class Skill(TypedDict):
    name: str
    type: str
    cost: int
    power: int
    cooldown: int
    accuracy: int
    target: str
    effect: NotRequired[str]
    effectChance: int
    duration: int
    requirements: dict[str, int]


class NPC(TypedDict):
    name: str
    identity: str
    location: str
    realm: str
    personality: str
    schedule: dict[str, int]
    quests: list[str]
    dialogueState: dict


class Quest(TypedDict):
    name: str
    description: str
    location: str
    type: str
    reward: int
    reputation: int
    requirements: dict
    penalties: dict


class ContractBeast(TypedDict):
    id: str
    name: str
    level: int
    xp: int
    loyalty: int
    personality: str
    skills: list[str]
    status: str
    statusEffects: list[StatusEffect]
    injuries: int
    hp: int
    maxHp: int
    lastFed: int
    stance: str
    force: bool


class RouteState(TypedDict):
    route: str | None
    mainDisciplines: list[str]
    proficiency: dict[str, int]
    techniqueLevels: dict[str, int]
    preparedFormation: dict | None
    beast: ContractBeast | None
    materialRemainders: dict[str, int]
    conduct: dict
    credibility: dict
