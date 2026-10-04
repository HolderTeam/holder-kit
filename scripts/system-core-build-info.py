#!/usr/bin/env python3
"""Record the installed core used by a system-library Python build."""

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.version:
        parser.error("the installed core CMake package did not report its version")
    info = {
        "source": "system-library",
        "version": args.version,
        "soname": "libholder.so.0",
        "schema_sha256": hashlib.sha256(args.schema.read_bytes()).hexdigest(),
    }
    if shutil.which("dpkg-query"):
        result = subprocess.run(
            ["dpkg-query", "-W", "-f=${Version}", "libholder-dev"],
            capture_output=True, text=True, check=False,
        )
        if result.returncode == 0:
            info["debian_package"] = "libholder-dev"
            info["debian_version"] = result.stdout.strip()
    args.output.write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
