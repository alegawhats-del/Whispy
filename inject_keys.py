# -*- coding: utf-8 -*-
"""Сборка: подставляет встроенные ключи бесплатных тарифов из секрета FREE_KEYS (JSON {"имя провайдера": "ключ"}) в app.py.
В репозитории ключей нет — только в собранном exe."""
import json
import os
import sys

raw = os.environ.get("FREE_KEYS", "").strip()
if not raw:
    print("FREE_KEYS not set - no builtin keys")
    sys.exit(0)
try:
    keys = json.loads(raw)
    assert isinstance(keys, dict)
except Exception as e:  # noqa: BLE001
    print("FREE_KEYS is not valid JSON object:", e)
    sys.exit(1)
with open("app.py", encoding="utf-8") as f:
    src = f.read()
marker = "BUILTIN_KEYS = {}"
if marker not in src:
    print("marker not found")
    sys.exit(1)
src = src.replace(marker, "BUILTIN_KEYS = " + json.dumps(keys, ensure_ascii=False), 1)
with open("app.py", "w", encoding="utf-8") as f:
    f.write(src)
print("builtin keys injected:", ", ".join(keys.keys()))
