#!/usr/bin/env python3
"""Carry the runtime suppliers' notices into Windows and macOS wheels."""

import argparse
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile


def run(*command: str) -> str:
    return subprocess.check_output(command, text=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    wheel = args.wheel.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="kit-notices-") as directory:
        temp = Path(directory)
        run(sys.executable, "-m", "wheel", "unpack", str(wheel), "-d", str(temp))
        root = next(temp.glob("holder_kit-*"))
        metadata = next(root.glob("*.dist-info"))
        notices = metadata / "licenses/third-party"
        notices.mkdir(parents=True)
        if sys.platform == "win32":
            source = Path(os.environ["HOLDER_CORE_SDK"]) / "share/vcpkg-licenses"
            if not list(source.glob("*.txt")):
                raise RuntimeError("SDK runtime notices are missing")
            shutil.copytree(source, notices / "vcpkg")
        elif sys.platform == "darwin":
            paths = run("delocate-listdeps", "--all", str(wheel)).splitlines()
            # Include the header-only JSON library compiled into the core SDK.
            paths.append(run("brew", "--prefix", "nlohmann-json").strip())
            suppliers: set[Path] = set()
            for line in paths:
                path = Path(line.strip())
                if not path.exists():
                    continue
                path = path.resolve()
                if "Cellar" in path.parts:
                    position = path.parts.index("Cellar")
                    suppliers.add(Path(*path.parts[:position + 3]))
            if not suppliers:
                raise RuntimeError("No Homebrew runtime suppliers found")
            for supplier in sorted(suppliers):
                files = [p for p in supplier.rglob("*") if p.is_file() and any(
                    word in p.name.upper() for word in ("LICENSE", "LICENCE", "COPYING", "COPYRIGHT", "NOTICE")
                )]
                if not files:
                    raise RuntimeError(f"No runtime notice found in {supplier}")
                for file in files:
                    target = notices / supplier.parent.name / file.relative_to(supplier)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(file, target)
        else:
            parser.error("Linux notices are collected by repair-linux-wheel.py")
        meta_file = metadata / "METADATA"
        header, separator, body = meta_file.read_text().partition("\n\n")
        for file in sorted(notices.rglob("*")):
            if file.is_file():
                header += f"\nLicense-File: {file.relative_to(metadata / 'licenses').as_posix()}"
        meta_file.write_text(header + separator + body)
        run(sys.executable, "-m", "wheel", "pack", str(root), "-d", str(output))


if __name__ == "__main__":
    main()
