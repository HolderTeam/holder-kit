#!/usr/bin/env python3
"""Forward the developer CLI to core's shared SDK consumer tool."""

import os
from pathlib import Path
import runpy
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.develop import AdviceError, Developer, ROOT

try:
    path = Developer(ROOT, os.environ).sdk_tool()
except AdviceError as error:
    raise SystemExit(str(error)) from error
runpy.run_path(str(path), run_name="__main__")
