"""Verify the complete release set and record its core pin and file hashes."""

import argparse
from email.parser import Parser
import hashlib
import json
from pathlib import Path
import tarfile
import tomllib
import zipfile
import subprocess

from pypi_readme import render_readme


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    version = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]
    pin = json.loads(Path("release-core.json").read_text())
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    description = render_readme(Path("README.md").read_text(encoding="utf-8"), Path.cwd(), commit)
    platforms = {"manylinux_2_39_x86_64", "win_amd64", "macosx_15_0_arm64"}
    expected = {(python, platform) for python in ("cp310", "cp311", "cp312", "cp313", "cp314")
                for platform in platforms}
    found: set[tuple[str, str]] = set()
    files = sorted(args.directory.iterdir())
    for file in files:
        if file.suffix != ".whl":
            continue
        name, file_version, python, abi, platform = file.stem.split("-")
        assert name == "holder_kit" and file_version == version, file
        assert python == abi and (python, platform) in expected, file
        assert (python, platform) not in found, file
        found.add((python, platform))
        with zipfile.ZipFile(file) as wheel:
            info = json.loads(wheel.read("holderkit/_core_build.json"))
            assert info["commit"] == pin["commit"] and info["build_type"] == "Release", file
            metadata = Parser().parsestr(wheel.read(f"holder_kit-{version}.dist-info/METADATA").decode())
            assert metadata["Name"] == "holder-kit" and metadata["Version"] == version, file
            assert metadata.get_payload().replace("\r\n", "\n").strip() == description.strip(), f"Unresolved or inconsistent README in {file}"
            assert any("third-party/" in notice for notice in metadata.get_all("License-File", [])), file
    assert found == expected, f"Missing wheels: {expected - found}"
    source = args.directory / f"holder_kit-{version}.tar.gz"
    assert source.is_file() and len(files) == len(expected) + 1, files
    with tarfile.open(source) as archive:
        entry = archive.extractfile(f"holder_kit-{version}/release-core.json")
        assert entry is not None and json.load(entry) == pin, "Source archive core pin differs"
        readme = archive.extractfile(f"holder_kit-{version}/README.md")
        assert readme is not None and readme.read().decode().strip() == description.strip(), "Source README differs"
        pkg_info = archive.extractfile(f"holder_kit-{version}/PKG-INFO")
        assert pkg_info is not None
        metadata = Parser().parsestr(pkg_info.read().decode())
        assert metadata.get_payload().strip() == description.strip(), "Source metadata README differs"
    manifest = {
        "version": version,
        "core": pin,
        "files": [{"name": file.name, "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
                   "size": file.stat().st_size} for file in files],
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Verified {len(found)} wheels and source archive for holder-kit {version}")


if __name__ == "__main__":
    main()
