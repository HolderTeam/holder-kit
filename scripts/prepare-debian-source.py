#!/usr/bin/env python3
"""Prepare a versioned, core-pinned Ubuntu source package from committed files."""

import argparse
from email.utils import formatdate
import gzip
from pathlib import Path
import re
import shutil
import subprocess
import tomllib


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--package-revision", required=True)
    parser.add_argument("--series", required=True, choices=("noble", "resolute"))
    parser.add_argument("--core-package-version", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    if args.version != version or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        parser.error("version must match the stable numeric pyproject.toml version")
    if not re.fullmatch(r"[1-9]\d*", args.package_revision):
        parser.error("package revision must be a positive integer")
    if not re.fullmatch(rf"\d+\.\d+\.\d+-[1-9]\d*~{args.series}1", args.core_package_version):
        parser.error("core package version must identify an exact package for this series")
    subprocess.run(["git", "diff", "--exit-code", "HEAD", "--"], cwd=root, check=True)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    shutil.copytree(root / "packaging/linux/debian", root / "debian")
    control = root / "debian/control"
    build_dependencies = control.read_text()
    expected_dependency = "libholder-dev (>= 0.2.0)"
    if build_dependencies.count(expected_dependency) != 1:
        parser.error("packaging control changed; cannot apply the core version pin")
    control.write_text(build_dependencies.replace(
        expected_dependency, f"libholder-dev (= {args.core_package_version})",
    ))
    package_version = f"{version}-{args.package_revision}~{args.series}1"
    (root / "debian/changelog").write_text(
        f"holder-kit ({package_version}) {args.series}; urgency=medium\n\n"
        f"  * Build Python bindings from {revision}.\n"
        f"  * Build against libholder-dev {args.core_package_version}.\n\n"
        f" -- Holder Team <holdercardteam@gmail.com>  {formatdate(localtime=True)}\n",
    )
    archive = subprocess.check_output(
        ["git", "archive", "--format=tar", f"--prefix=holder-kit-{version}/", "HEAD"], cwd=root,
    )
    (root.parent / f"holder-kit_{version}.orig.tar.gz").write_bytes(gzip.compress(archive, mtime=0))


if __name__ == "__main__":
    main()
