#!/usr/bin/env python3
"""Bundle the Linux dependency closure, then validate and tag with auditwheel.

auditwheel permits system GLib, which minimal Python environments need not have.
Give every bundled library a private SONAME so the wheel carries these libraries
without depending on a distribution's GLib or C++ runtime installation.
"""

import argparse
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


# The host's glibc and loader supply these. All other dependencies are bundled.
SYSTEM_LIBRARIES = {
    "libc.so.6", "libm.so.6", "libdl.so.2", "libpthread.so.0", "librt.so.1",
    "libresolv.so.2", "libutil.so.1", "libanl.so.1",
}


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
    with tempfile.TemporaryDirectory(prefix="kit-wheel-") as directory:
        temp = Path(directory)
        run(sys.executable, "-m", "wheel", "unpack", str(wheel), "-d", str(temp))
        root = next(temp.glob("holder_kit-*"))
        native = next((root / "holderkit").glob("_native*.so"))
        dependencies: dict[str, Path] = {}
        for line in run("ldd", str(native)).splitlines():
            if "not found" in line:
                raise RuntimeError(f"Unresolved build dependency: {line}")
            match = re.match(r"\s*(\S+) => (/\S+) \(", line)
            if match and match[1] not in SYSTEM_LIBRARIES:
                dependencies[match[1]] = Path(match[2]).resolve()
        if not dependencies:
            raise RuntimeError("Expected the core SDK's shared runtime dependencies")
        libraries = root / "holderkit/.libs"
        libraries.mkdir(exist_ok=True)
        metadata = next(root.glob("*.dist-info"))
        notices = metadata / "licenses/third-party"
        notices.mkdir(parents=True)
        names: dict[str, str] = {}
        packages = {"nlohmann-json3-dev"}
        for soname, source in dependencies.items():
            digest = hashlib.sha256(source.read_bytes()).hexdigest()[:12]
            stem, suffix = soname.split(".so", 1)
            private_name = f"{stem}-kit-{digest}.so{suffix}"
            names[soname] = private_name
            destination = libraries / private_name
            shutil.copy2(source, destination)
            run("patchelf", "--set-soname", private_name, str(destination))
            owner = run("dpkg-query", "-S", str(source)).splitlines()[0].rsplit(": ", 1)[0]
            packages.add(owner)
        for library in [native, *libraries.iterdir()]:
            needed = run("patchelf", "--print-needed", str(library)).splitlines()
            for original in needed:
                if original in names:
                    run("patchelf", "--replace-needed", original, names[original], str(library))
            relative_path = "$ORIGIN/.libs" if library == native else "$ORIGIN"
            run("patchelf", "--force-rpath", "--set-rpath", relative_path, str(library))
        for package in sorted(packages):
            name = package.split(":", 1)[0]
            copyright_file = Path("/usr/share/doc") / name / "copyright"
            if not copyright_file.is_file():
                raise RuntimeError(f"Missing runtime copyright notice for {package}")
            shutil.copy2(copyright_file, notices / f"{name}.copyright")
        # Debian copyright files refer to these complete licence texts.
        shutil.copytree("/usr/share/common-licenses", notices / "common-licenses")
        meta_file = metadata / "METADATA"
        header, separator, body = meta_file.read_text().partition("\n\n")
        for notice in sorted(notices.rglob("*")):
            if notice.is_file():
                header += f"\nLicense-File: {notice.relative_to(metadata / 'licenses').as_posix()}"
        meta_file.write_text(header + separator + body)
        packed = temp / "packed"
        packed.mkdir()
        run(sys.executable, "-m", "wheel", "pack", str(root), "-d", str(packed))
        run(sys.executable, "-m", "auditwheel", "repair", "--only-plat",
            "--plat", "manylinux_2_39_x86_64", "--wheel-dir", str(output),
            str(next(packed.glob("*.whl"))))


if __name__ == "__main__":
    main()
