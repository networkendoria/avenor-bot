#!/usr/bin/env python3
"""Merge one bot run's state delta onto the newest state.json."""
import json
import sys

base_path, local_path, remote_path, output_path = sys.argv[1:5]

def read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

base = read(base_path)
local = read(local_path)
remote = read(remote_path)

base_date = base.get("date", "")
local_date = local.get("date", "")
remote_date = remote.get("date", "")

if local_date >= remote_date:
    merged = dict(remote)
    merged.update({k: v for k, v in local.items() if k not in ("minutes", "history")})
    merged["date"] = local_date
    if local_date == remote_date:
        minutes = dict(remote.get("minutes", {}))
        before = base.get("minutes", {})
        after = local.get("minutes", {})
        for name in set(before) | set(after):
            delta = float(after.get(name, 0)) - float(before.get(name, 0))
            if delta > 0:
                minutes[name] = round(float(minutes.get(name, 0)) + delta, 3)
            elif name not in minutes and name in after:
                minutes[name] = after[name]
        merged["minutes"] = minutes
    else:
        merged["minutes"] = dict(local.get("minutes", {}))
else:
    merged = dict(local)
    merged["date"] = remote_date
    merged["minutes"] = dict(remote.get("minutes", {}))

history = dict(remote.get("history", {}))
for day, people in local.get("history", {}).items():
    target = dict(history.get(day, {}))
    for name, minutes in people.items():
        target[name] = max(float(target.get(name, 0)), float(minutes))
    history[day] = target
merged["history"] = history

markers = [x for x in (local.get("last_monthly"), remote.get("last_monthly")) if x]
merged["last_monthly"] = max(markers) if markers else None
merged.setdefault("minutes", {})

with open(output_path, "w", encoding="utf-8") as f:
    json.dump(merged, f, ensure_ascii=False, indent=2)
    f.write("\\n")
