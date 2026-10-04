"""Content pack loader.

Each pack (content / island) lives in systems/xiuxian/<pack>/*.json shards.
Shards are shallow-merged by top-level key in filename order, so gameplay
domains can live in separate files without any loader-side special cases."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "systems/xiuxian"


def load_pack(pack):
    merged = {}
    for shard in sorted((ROOT / pack).glob("*.json")):
        merged.update(json.loads(shard.read_text(encoding="utf-8")))
    return merged
