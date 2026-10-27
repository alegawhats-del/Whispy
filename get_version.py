# -*- coding: utf-8 -*-
"""Печатает APP_VERSION из app.py — для батников сборки."""
import os
import re

here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, "app.py"), encoding="utf-8") as f:
    src = f.read()
m = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', src)
print(m.group(1) if m else "0.0.0")
