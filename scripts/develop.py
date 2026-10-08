#!/usr/bin/env python3
"""Portable developer entry point; native dependency knowledge stays in core."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from typing import Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
BUILD_TYPES = {"Debug", "Release", "RelWithDebInfo", "MinSizeRel"}
BUILD_COMMANDS = {"setup", "build", "test", "check", "wheel"}
EXAMPLES = {
    "lifecycle": "card_lifecycle", "records": "detached_records",
    "pandas": "pandas_analysis", "graph": "graph_analysis",
    "tags": "tag_analysis",
    "milestones": "milestone_analysis",
    "workspace": "private_workspace",
}
HELP = """Holder Kit developer commands

Usage: ./make.sh [--sdk] [command] [BuildType] [args...]

Commands:
  help, -h, --help          Show help without creating environments or downloading
  setup, build [BuildType] Create/reuse .venv and build editable test extras
  test [BuildType] [args]  Build and run pytest (default); forward args to pytest
  check [BuildType]        Build, run tests and strict mypy
  typecheck [args]         Run mypy using the installed development environment
  wheel [BuildType]        Build a wheel into out/make/wheels
  examples [name]          Run all examples, or lifecycle, records, pandas, graph,
                           tags, milestones, workspace
  setup-core              Prepare a pinned checkout in build/deps/holder-core
  sdk [core-ref]           Resolve and fetch an SDK (default latest-green)
  clean                   Remove build/make and out/make only

Default core discovery:
  HOLDER_KIT_CORE_SOURCE, then ../holder-core, then build/deps/holder-core.
  Missing core stops with instructions before creating a venv or installing.
  Existing source checkouts are never switched, pulled or reset.
  --sdk, HOLDER_CORE_SDK or HOLDER_CORE_REF explicitly select the SDK workflow.

Examples:
  ./make.sh
  ./make.sh setup-core
  ./make.sh check
  ./make.sh test Debug -k connections
  ./make.sh examples graph
  ./make.sh --sdk wheel Release

Environment:
  HOLDER_KIT                 Bootstrap Python (3.10+); otherwise reuse .venv
  HOLDER_KIT_VENV            Venv path (default .venv)
  HOLDER_KIT_CORE_SOURCE     Override the discovered core source path
  HOLDER_CORE_SDK            Explicit prepared SDK directory
  HOLDER_CORE_REF            Explicit SDK tag/SHA or latest-green
  HOLDER_CORE_SDK_TOOL       Override core's shared SDK consumer script
  BUILD_TYPE                Default RelWithDebInfo; also Debug, Release, MinSizeRel
  CMAKE_BUILD_PARALLEL_LEVEL Optional build parallelism limit

setup-core uses core-source.json and never updates an existing checkout.
clean retains the managed core checkout, .venv and SDK cache.
Source builds use core's CMake checks and README for native prerequisites.
SDK builds use Release for Release/MinSizeRel, otherwise RelWithDebInfo.
Pip installation and explicit setup-core/SDK fetching can require network access.
"""


class AdviceError(Exception):
    """A developer prerequisite or usage problem with an actionable message."""


class Developer:
    def __init__(self, root: Path, env: Mapping[str, str]) -> None:
        self.root = root.resolve()
        self.env = dict(env)
        self.env["PYTHONDONTWRITEBYTECODE"] = "1"
        self.build_type = self.env.get("BUILD_TYPE") or "RelWithDebInfo"
        self.venv = self.path(self.env.get("HOLDER_KIT_VENV") or ".venv")
        self.managed = self.root / "build/deps/holder-core"

    def path(self, value: str) -> Path:
        path = Path(value).expanduser()
        return path if path.is_absolute() else self.root / path

    def run(self, args: Sequence[str], *, capture: bool = False) -> str:
        result = subprocess.run(
            args, cwd=self.root, env=self.env, text=True,
            capture_output=capture, check=True,
        )
        return result.stdout.strip() if capture else ""

    def git(self, source: Path, *args: str) -> str:
        saved = self.env.copy()
        for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
            self.env.pop(key, None)
        try:
            return self.run(["git", "-C", str(source), *args], capture=True)
        finally:
            self.env = saved

    def pin(self) -> dict[str, str]:
        data = json.loads((self.root / "core-source.json").read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("commit"), str) or data.get("repository") != "https://github.com/HolderTeam/holder-core.git" or not re.fullmatch(
            r"[0-9a-f]{40}", data.get("commit", ""),
        ):
            raise AdviceError("core-source.json must contain the official core URL and a full commit SHA.")
        return {"repository": data["repository"], "commit": data["commit"]}

    def validate_source(self, source: Path) -> Path:
        source = source.resolve()
        required = ("CMakeLists.txt", "include/holder/holder.h", "schema/schema.sql", "README.md")
        if not all((source / name).is_file() for name in required):
            raise AdviceError(
                f"Not a usable holder-core source checkout: {source}\n"
                "Check the path or finish checking out holder-core; an invalid explicit/sibling path is not skipped."
            )
        return source

    def discover_source(self) -> Path:
        explicit = self.env.get("HOLDER_KIT_CORE_SOURCE")
        if explicit:
            return self.validate_source(self.path(explicit))
        for candidate in (self.root.parent / "holder-core", self.managed):
            if candidate.exists() or candidate.is_symlink():
                return self.validate_source(candidate)
        sibling = self.root.parent / "holder-core"
        raise AdviceError(
            "holder-core source is required for the default developer build.\n\n"
            "Clone it beside the Holder Kit checkout:\n"
            f"  git clone https://github.com/HolderTeam/holder-core.git {shlex.quote(str(sibling))}\n\n"
            "Or prepare the tested revision inside this repository:\n"
            "  ./make.sh setup-core\n\n"
            "Then run ./make.sh again. For a different checkout, set HOLDER_KIT_CORE_SOURCE.\n"
            "Published SDK builds are available explicitly with ./make.sh --sdk."
        )

    def source_revision(self, source: Path) -> tuple[str | None, bool]:
        if not shutil.which("git", path=self.env.get("PATH")):
            return None, False
        try:
            if Path(self.git(source, "rev-parse", "--show-toplevel")).resolve() != source:
                return None, False
            return self.git(source, "rev-parse", "HEAD"), bool(self.git(source, "status", "--porcelain"))
        except subprocess.CalledProcessError:
            return None, False

    def report_source(self, source: Path) -> dict[str, object]:
        pin = self.pin()["commit"]
        commit, dirty = self.source_revision(source)
        if source == self.managed.resolve() and commit != pin and not self.env.get("HOLDER_KIT_CORE_SOURCE"):
            raise AdviceError(
                f"Managed core checkout is not at the recorded commit {pin}.\n"
                "It will not be changed. Move it aside and run ./make.sh setup-core, or select it\n"
                "explicitly with HOLDER_KIT_CORE_SOURCE to use it as a developer checkout."
            )
        print(f"Core source: {source}", flush=True)
        print(f"Core revision: {commit or 'unknown (not a Git checkout)'}{' (working tree has changes)' if dirty else ''}", flush=True)
        if commit != pin or dirty:
            print(f"Recorded tested core: {pin}; using your selected checkout without changing it.", flush=True)
        return {"path": str(source), "commit": commit, "dirty": dirty, "tested_commit": pin}

    def prerequisite_advice(self, source: Path | None) -> str:
        message = "Install Python development headers, a C/C++20 compiler, CMake 3.22+ and pkg-config."
        if source:
            message += f"\nCore's authoritative native dependency instructions: {source / 'README.md'}"
        system = platform.system()
        if system == "Darwin":
            message += "\nOn macOS, install Xcode Command Line Tools and core's Homebrew dependencies."
            message += "\nUse CMAKE_PREFIX_PATH for Homebrew/keg-only libraries when CMake cannot find them."
        elif system.endswith("BSD") or system == "DragonFly":
            message += "\nOn BSD, use your ports/package manager for the development packages named by CMake."
        return message

    def check_tools(self, source: Path | None) -> None:
        tools = [
            ("CMake", "cmake"), ("C compiler", self.env.get("CC") or "cc"),
            ("C++ compiler", self.env.get("CXX") or "c++"),
        ]
        if platform.system() != "Windows":
            tools.append(("pkg-config", "pkg-config"))
        missing = [name for name, command in tools if not shutil.which(
            shlex.split(command)[0], path=self.env.get("PATH"),
        )]
        if missing:
            raise AdviceError(f"Missing build tools: {', '.join(missing)}.\n{self.prerequisite_advice(source)}")
        version = re.search(r"cmake version (\d+)\.(\d+)", self.run(["cmake", "--version"], capture=True))
        if version is None or tuple(map(int, version.groups())) < (3, 22):
            raise AdviceError("CMake 3.22 or newer is required. Upgrade CMake and rerun ./make.sh.")
        try:
            python = self.venv_python() if self.venv_python().is_file() else Path(sys.executable)
            self.run([str(python), "-c", "import venv, sysconfig; from pathlib import Path; "
                      "assert (Path(sysconfig.get_path('include')) / 'Python.h').is_file(), "
                      "'Python development headers (Python.h) are missing'"])
        except subprocess.CalledProcessError as error:
            raise AdviceError(f"Python venv/development prerequisites are missing.\n{self.prerequisite_advice(source)}") from error
        if platform.system() == "Darwin" and shutil.which("brew", path=self.env.get("PATH")):
            try:
                prefix = Path(self.run(["brew", "--prefix"], capture=True))
            except subprocess.CalledProcessError:
                return
            prefixes = [prefix, prefix / "opt/openssl@3", prefix / "opt/openssl"]
            existing = self.env.get("CMAKE_PREFIX_PATH", "")
            paths = [str(path) for path in prefixes if path.is_dir()]
            self.env["CMAKE_PREFIX_PATH"] = os.pathsep.join(([existing] if existing else []) + paths)

    def preflight_source(self, source: Path) -> None:
        self.check_tools(source)
        identity = hashlib.sha256(str(source).encode()).hexdigest()[:12]
        directory = self.root / f"build/make/prerequisites/{identity}/{self.build_type}"
        try:
            self.run([
                "cmake", "-S", str(source), "-B", str(directory),
                "-DBUILD_TESTING=OFF", f"-DCMAKE_BUILD_TYPE={self.build_type}",
            ])
        except subprocess.CalledProcessError as error:
            raise AdviceError(
                "Core's CMake prerequisite check failed; no Python packages have been installed.\n"
                f"{self.prerequisite_advice(source)}\nFix the error above and rerun ./make.sh."
            ) from error

    def venv_python(self) -> Path:
        windows = self.venv / "Scripts/python.exe"
        return windows if windows.is_file() else self.venv / "bin/python"

    def require_venv(self) -> Path:
        python = self.venv_python()
        if not python.is_file():
            raise AdviceError(f"No virtualenv at {self.venv}. Run ./make.sh setup first.")
        return python

    def prepare_venv(self) -> Path:
        if not self.venv_python().is_file():
            if self.venv.exists() or self.venv.is_symlink():
                raise AdviceError(f"{self.venv} exists but has no virtualenv Python; choose HOLDER_KIT_VENV.")
            try:
                self.run([sys.executable, "-m", "venv", str(self.venv)])
            except subprocess.CalledProcessError as error:
                raise AdviceError("Could not create the virtualenv. Install your Python venv/ensurepip package and retry.") from error
        return self.require_venv()

    def sdk_tool(self) -> Path:
        explicit = self.env.get("HOLDER_CORE_SDK_TOOL")
        candidates = [self.path(explicit)] if explicit else [
            self.root.parent / "holder-core/scripts/core-sdk.py",
            self.managed / "scripts/core-sdk.py",
        ]
        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()
        raise AdviceError(
            "The SDK workflow needs core's shared scripts/core-sdk.py.\n"
            "Clone ../holder-core, run ./make.sh setup-core, or set HOLDER_CORE_SDK_TOOL."
        )

    def fetch_sdk(self, python: Path, tool: Path) -> None:
        config = "Release" if self.build_type in {"Release", "MinSizeRel"} else "RelWithDebInfo"
        self.env["HOLDER_CORE_SDK"] = self.run([
            str(python), str(tool), "fetch", "--build-type", config,
        ], capture=True)

    def prepare_sdk(self) -> None:
        if self.env.get("HOLDER_CORE_SDK") and not (self.path(self.env["HOLDER_CORE_SDK"]) / "libholder-manifest.json").is_file():
            raise AdviceError("HOLDER_CORE_SDK must name a prepared SDK containing libholder-manifest.json.")
        tool = self.sdk_tool() if not self.env.get("HOLDER_CORE_SDK") else None
        self.check_tools(None)
        python = self.prepare_venv()
        if tool:
            if not (self.root / "out/core-selection.json").is_file() or self.env.get("HOLDER_CORE_REF"):
                self.run([str(python), str(tool), "resolve"])
            self.fetch_sdk(python, tool)
        sdk = self.path(self.env["HOLDER_CORE_SDK"]).resolve()
        if not (sdk / "libholder-manifest.json").is_file():
            raise AdviceError(f"SDK directory must contain libholder-manifest.json: {sdk}")
        self.env["HOLDER_CORE_SDK"] = str(sdk)
        print(f"Core SDK: {sdk}", flush=True)

    def build_settings(self, source: Path | None) -> list[str]:
        backend = "source" if source else "sdk"
        settings = [
            f"--config-settings=build-dir=build/make/{backend}/{self.build_type}/{{wheel_tag}}",
            f"--config-settings=cmake.build-type={self.build_type}",
            f"--config-settings=cmake.define.HOLDER_KIT_CORE_SOURCE={source or ''}",
            "--config-settings=cmake.define.HOLDER_KIT_SANITIZE=",
        ]
        if not source and platform.system() == "Windows":
            sdk = Path(self.env["HOLDER_CORE_SDK"]).as_posix()
            settings.extend([
                f"--config-settings=cmake.define.CMAKE_TOOLCHAIN_FILE={sdk}/vcpkg/scripts/buildsystems/vcpkg.cmake",
                f"--config-settings=cmake.define.VCPKG_INSTALLED_DIR={sdk}/vcpkg/installed",
                "--config-settings=cmake.define.VCPKG_TARGET_TRIPLET=x64-windows",
                "--config-settings=cmake.define.VCPKG_MANIFEST_MODE=OFF",
                "--config-settings=cmake.define.VCPKG_APPLOCAL_DEPS=OFF",
            ])
        return settings

    def build(self, mode: str, sdk: bool) -> Path:
        source = None
        if sdk:
            self.prepare_sdk()
        else:
            source = self.discover_source()
            provenance = self.report_source(source)
            self.preflight_source(source)
            output = self.root / "out/make/core-source.json"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
            self.env.pop("HOLDER_CORE_SDK", None)
        python = self.prepare_venv()
        args = [str(python), "-m", "pip"]
        args += ["wheel", "--no-deps", ".", "--wheel-dir", "out/make/wheels"] if mode == "wheel" else ["install", "-e", ".[test]"]
        self.run(args + self.build_settings(source))
        return python

    def setup_core(self) -> None:
        pin = self.pin()
        for relative in ("build", "build/deps", "build/deps/holder-core"):
            if (self.root / relative).is_symlink():
                raise AdviceError(f"Refusing to prepare a managed checkout through symlinked {relative}.")
        if not shutil.which("git", path=self.env.get("PATH")):
            raise AdviceError("Install Git to use ./make.sh setup-core, or provide an existing core source checkout.")
        if self.managed.exists():
            source = self.validate_source(self.managed)
            commit, dirty = self.source_revision(source)
            if commit != pin["commit"] or dirty:
                raise AdviceError("Existing managed core checkout differs from the clean recorded revision.\n"
                                  "It will not be changed; move it aside or use HOLDER_KIT_CORE_SOURCE.")
            print(f"Managed core is already ready at {commit}: {source}", flush=True)
            return
        self.managed.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="holder-core-", dir=self.managed.parent) as temporary:
            staging = Path(temporary) / "checkout"
            staging.mkdir()
            self.git(staging, "init")
            self.git(staging, "remote", "add", "origin", pin["repository"])
            self.git(staging, "fetch", "--depth=1", "origin", pin["commit"])
            self.git(staging, "checkout", "--detach", "FETCH_HEAD")
            self.validate_source(staging)
            if self.git(staging, "rev-parse", "HEAD") != pin["commit"]:
                raise AdviceError("Fetched core revision does not match core-source.json.")
            if self.managed.exists() or self.managed.is_symlink():
                raise AdviceError("Managed destination appeared during setup; it will not be overwritten.")
            staging.rename(self.managed)
        print(f"Prepared core {pin['commit']} at {self.managed}. Run ./make.sh next.", flush=True)

    def clean(self) -> None:
        for parent in ("build", "out"):
            if (self.root / parent).is_symlink() or (self.root / parent / "make").is_symlink():
                raise AdviceError(f"Refusing to clean symlinked {parent}/make.")
        for relative in ("build/make", "out/make"):
            target = self.root / relative
            if target.exists():
                shutil.rmtree(target)
        print("Removed build/make and out/make; managed core, virtualenv and SDK cache retained.")


def main(args: Sequence[str] | None = None, *, root: Path = ROOT, env: Mapping[str, str] | None = None) -> int:
    arguments = list(sys.argv[1:] if args is None else args)
    sdk_flag = bool(arguments and arguments[0] == "--sdk")
    if sdk_flag:
        arguments.pop(0)
    mode = arguments.pop(0) if arguments else "test"
    if mode in {"help", "-h", "--help"}:
        print(HELP)
        return 0
    developer = Developer(root, os.environ if env is None else env)
    try:
        if mode not in BUILD_COMMANDS | {"typecheck", "examples", "sdk", "clean", "setup-core"}:
            raise AdviceError(f"Unknown command: {mode}. Run ./make.sh --help.")
        if mode in BUILD_COMMANDS and arguments and arguments[0] in BUILD_TYPES:
            developer.build_type = arguments.pop(0)
        if developer.build_type not in BUILD_TYPES:
            raise AdviceError(f"Invalid BUILD_TYPE: {developer.build_type}")
        if mode in {"setup", "build", "check", "wheel", "clean", "setup-core"} and arguments:
            raise AdviceError(f"Unexpected arguments for {mode}: {shlex.join(arguments)}")
        if mode in {"sdk", "examples"} and len(arguments) > 1:
            raise AdviceError(f"{mode} accepts one argument")
        if sdk_flag and mode not in BUILD_COMMANDS | {"sdk"}:
            raise AdviceError("--sdk applies to setup/build/test/check/wheel or sdk.")
        if sdk_flag and developer.env.get("HOLDER_KIT_CORE_SOURCE"):
            raise AdviceError("Choose --sdk or HOLDER_KIT_CORE_SOURCE, not both.")
        sdk = sdk_flag or (not developer.env.get("HOLDER_KIT_CORE_SOURCE") and bool(
            developer.env.get("HOLDER_CORE_SDK") or developer.env.get("HOLDER_CORE_REF")))
        if mode in BUILD_COMMANDS:
            python = developer.build(mode, sdk)
            if mode in {"test", "check"}:
                developer.run([str(python), "-m", "pytest", *arguments])
            if mode == "check":
                developer.run([str(python), "-m", "mypy"])
        elif mode == "typecheck":
            developer.run([str(developer.require_venv()), "-m", "mypy", *arguments])
        elif mode == "examples":
            name = arguments[0] if arguments else "all"
            if name != "all" and name not in EXAMPLES:
                raise AdviceError(f"Unknown example: {name}. Choose all, lifecycle, records, pandas or graph.")
            python = developer.require_venv()
            for example in EXAMPLES.values() if name == "all" else [EXAMPLES[name]]:
                developer.run([str(python), f"examples/{example}.py"])
        elif mode == "setup-core":
            developer.setup_core()
        elif mode == "sdk":
            tool = developer.sdk_tool()
            python = developer.prepare_venv()
            ref = arguments[0] if arguments else developer.env.get("HOLDER_CORE_REF") or "latest-green"
            developer.run([str(python), str(tool), "resolve", "--core-ref", ref])
            developer.fetch_sdk(python, tool)
            print(f"SDK ready: {developer.env['HOLDER_CORE_SDK']}; use ./make.sh --sdk to build.")
        else:
            developer.clean()
    except AdviceError as error:
        print(error, file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as error:
        if error.stderr:
            print(error.stderr.rstrip(), file=sys.stderr)
        if error.stdout:
            print(error.stdout.rstrip(), file=sys.stderr)
        print(f"Command failed: {shlex.join(error.cmd)} (exit {error.returncode}).", file=sys.stderr)
        print("Fix the error above, then rerun ./make.sh. See ./make.sh --help for setup options.", file=sys.stderr)
        return error.returncode if error.returncode > 0 else 1
    except (OSError, ValueError) as error:
        print(f"Setup failed: {error}. Check the paths and prerequisites shown by ./make.sh --help.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
