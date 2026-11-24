"""Genera v0.json, v1.json... a partir de p.json con overrides (para comparar looks en la toma hero)."""
import json, os
base = json.load(open("p.json"))
for i, v in enumerate(json.loads(os.environ["VARIANTES"])):
    q = dict(base); q.update(v); q["shots"] = [{"name": "hero", "frames": 30}]
    q["id"] = base["id"] + "_v%d_" % i + "_".join(f"{k}{v[k]}" for k in v)
    json.dump(q, open(f"v{i}.json", "w"))
    print(q["id"])
