"""One-time character birth rolls, independent from combat randomness."""

import secrets


def generate_root(config, randbelow=None):
    randbelow = randbelow or secrets.randbelow
    roll = randbelow(100)
    cumulative = 0
    for count, weight in enumerate(config["countWeights"], start=1):
        cumulative += weight
        if roll < cumulative:
            break
    remaining = list(config["elements"])
    chosen = []
    for _ in range(count):
        chosen.append(remaining.pop(randbelow(len(remaining))))
    chosen = [element for element in config["elements"] if element in chosen]
    suffix = {1: "单灵根", 2: "双灵根", 3: "三灵根", 4: "四灵根", 5: "五灵根"}[count]
    return {"root": "".join(chosen) + suffix, "rootElements": chosen}


def generate_aptitude(config, randbelow=None):
    randbelow = randbelow or secrets.randbelow
    roll = randbelow(100)
    cumulative = 0
    for aptitude, weight in enumerate(config["aptitudeWeights"], start=1):
        cumulative += weight
        if roll < cumulative:
            return aptitude
    raise ValueError("Aptitude probabilities must total 100")
