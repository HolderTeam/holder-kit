#!/usr/bin/env python3
"""Forward the developer CLI to core's shared SDK consumer tool."""

import os
from pathlib import Path
import runpy

path = Path(os.environ.get("HOLDER_CORE_SDK_TOOL", Path(__file__).parents[2] / "holder-core/scripts/core-sdk.py"))
if not path.is_file():
    raise SystemExit("Clone holder-core beside holder-python, or set HOLDER_CORE_SDK_TOOL to its scripts/core-sdk.py")
runpy.run_path(str(path), run_name="__main__")
