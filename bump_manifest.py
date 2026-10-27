# -*- coding: utf-8 -*-
"""Пишет version.json для указанной версии: ссылка на установщик из Release + заметки из NOTES.md."""
import json
import sys
import datetime

ver = sys.argv[1].lstrip("v")
try:
    notes = open("NOTES.md", encoding="utf-8").read().strip()
except FileNotFoundError:
    notes = ""
data = {
    "version": ver,
    "date": datetime.date.today().isoformat(),
    "notes": notes,
    "setup": f"https://github.com/alegawhats-del/Whispy/releases/download/v{ver}/Whispy-Setup-{ver}.exe",
}
with open("version.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
    f.write("\n")
print(json.dumps(data, ensure_ascii=False, indent=2))
