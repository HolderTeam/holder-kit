"""Developer discovery/setup contracts, with build/network commands isolated."""

from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from typing import Sequence

import pytest

from scripts import develop


PIN = "a" * 40


def create_core(path: Path, revision: str = PIN) -> Path:
    for name in ("CMakeLists.txt", "include/holder/holder.h", "schema/schema.sql", "README.md", "scripts/core-sdk.py"):
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("fixture", encoding="utf-8")
    (path / ".git").mkdir(exist_ok=True)
    (path / ".revision").write_text(revision, encoding="utf-8")
    return path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "checkout with spaces"
    (root / "scripts").mkdir(parents=True)
    shutil.copyfile(develop.ROOT / "make.sh", root / "make.sh")
    shutil.copyfile(develop.ROOT / "scripts/develop.py", root / "scripts/develop.py")
    (root / "core-source.json").write_text(json.dumps({
        "repository": "https://github.com/HolderTeam/holder-core.git", "commit": PIN,
    }), encoding="utf-8")
    return root


class FakeCommands:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.envs: list[dict[str, str]] = []
        self.failure: str | None = None

    def run(self, developer: develop.Developer, args: Sequence[str], *, capture: bool = False) -> str:
        command = list(args)
        self.calls.append(command)
        self.envs.append(developer.env.copy())
        if self.failure and self.failure in command:
            raise subprocess.CalledProcessError(7, command)
        if command[0] == "git":
            source = Path(command[2])
            operation = command[3:]
            if operation == ["init"]:
                (source / ".git").mkdir()
            elif operation[0] == "fetch":
                create_core(source, operation[-1])
            elif operation == ["rev-parse", "--show-toplevel"]:
                return str(source)
            elif operation == ["rev-parse", "HEAD"]:
                return (source / ".revision").read_text()
            elif operation == ["status", "--porcelain"]:
                return " M README.md" if (source / ".dirty").exists() else ""
        elif command == ["cmake", "--version"]:
            return "cmake version 4.3.0"
        elif command[1:3] == ["-m", "venv"]:
            python = Path(command[-1]) / "bin/python"
            python.parent.mkdir(parents=True)
            python.touch()
        elif len(command) > 2 and command[2] == "resolve":
            (developer.root / "out").mkdir(exist_ok=True)
            (developer.root / "out/core-selection.json").write_text("{}")
        elif len(command) > 2 and command[2] == "fetch":
            sdk = developer.root / "prepared SDK"
            sdk.mkdir(exist_ok=True)
            (sdk / "libholder-manifest.json").write_text("{}")
            return str(sdk)
        elif command == ["brew", "--prefix"]:
            return str(developer.root / "homebrew")
        return ""


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeCommands:
    commands = FakeCommands()

    def run(developer: develop.Developer, args: Sequence[str], *, capture: bool = False) -> str:
        return commands.run(developer, args, capture=capture)

    monkeypatch.setattr(develop.Developer, "run", run)
    monkeypatch.setattr(shutil, "which", lambda command, path=None: f"/tools/{command}")
    return commands


def cli(repo: Path, *args: str, **env: str) -> int:
    return develop.main(args, root=repo, env=env)


@pytest.mark.parametrize("argument", ["help", "--help", "-h", "unknown"])
def test_help_invalid_command_and_no_side_effects(repo: Path, fake: FakeCommands, argument: str) -> None:
    assert cli(repo, argument) == (2 if argument == "unknown" else 0)
    assert not fake.calls
    assert not (repo / ".venv").exists()


def test_missing_core_advice_precedes_setup(repo: Path, fake: FakeCommands, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli(repo) == 2
    advice = capsys.readouterr().err
    assert "git clone" in advice and "./make.sh setup-core" in advice
    assert not fake.calls
    assert not (repo / ".venv").exists()


def test_sibling_default_and_arguments(repo: Path, fake: FakeCommands) -> None:
    sibling = create_core(repo.parent / "holder-core")
    (sibling / ".dirty").touch()
    assert cli(repo, "test", "Debug", "-k", "connections or graph") == 0
    assert fake.calls[-1][1:] == ["-m", "pytest", "-k", "connections or graph"]
    pip = next(call for call in fake.calls if "pip" in call)
    assert f"--config-settings=cmake.define.HOLDER_KIT_CORE_SOURCE={sibling}" in pip
    assert "--config-settings=cmake.build-type=Debug" in pip
    assert not any("fetch" in call or "checkout" in call or "pull" in call for call in fake.calls)
    provenance = json.loads((repo / "out/make/core-source.json").read_text())
    assert provenance["dirty"] is True and provenance["commit"] == PIN


def test_explicit_source_precedence_and_invalid_path(repo: Path, fake: FakeCommands) -> None:
    create_core(repo.parent / "holder-core")
    selected = create_core(repo / "custom core")
    assert cli(repo, "build", HOLDER_KIT_CORE_SOURCE="custom core", HOLDER_CORE_SDK="ignored") == 0
    assert f"--config-settings=cmake.define.HOLDER_KIT_CORE_SOURCE={selected}" in fake.calls[-1]
    assert "HOLDER_CORE_SDK" not in fake.envs[-1]
    fake.calls.clear()
    assert cli(repo, "build", HOLDER_KIT_CORE_SOURCE="missing") == 2
    assert not fake.calls


def test_invalid_sibling_does_not_fall_through(repo: Path, fake: FakeCommands) -> None:
    (repo.parent / "holder-core").mkdir()
    create_core(repo / "build/deps/holder-core")
    assert cli(repo) == 2
    assert not fake.calls


def test_managed_fallback_and_wrong_revision(repo: Path, fake: FakeCommands) -> None:
    managed = create_core(repo / "build/deps/holder-core")
    assert cli(repo, "check") == 0
    assert fake.calls[-1][1:] == ["-m", "mypy"]
    (managed / ".revision").write_text("b" * 40)
    fake.calls.clear()
    assert cli(repo) == 2
    assert not any("pip" in call or "checkout" in call for call in fake.calls)
    assert cli(repo, "build", HOLDER_KIT_CORE_SOURCE=str(managed)) == 0


def test_cmake_failure_precedes_venv_and_packages(repo: Path, fake: FakeCommands, capsys: pytest.CaptureFixture[str]) -> None:
    source = create_core(repo.parent / "holder-core")
    fake.failure = "-DBUILD_TESTING=OFF"
    assert cli(repo) == 2
    assert str(source / "README.md") in capsys.readouterr().err
    assert not (repo / ".venv").exists()
    assert not any("pip" in call for call in fake.calls)


def test_check_propagates_test_failure(repo: Path, fake: FakeCommands) -> None:
    create_core(repo.parent / "holder-core")
    fake.failure = "pytest"
    assert cli(repo, "check") == 7
    assert not any("mypy" in call for call in fake.calls)


def test_explicit_sdk_and_selection_reuse(repo: Path, fake: FakeCommands) -> None:
    create_core(repo.parent / "holder-core")
    assert cli(repo, "--sdk", "test") == 0
    assert any("resolve" in call for call in fake.calls)
    assert any("fetch" in call for call in fake.calls)
    assert not any("-DBUILD_TESTING=OFF" in call for call in fake.calls)
    fake.calls.clear()
    assert cli(repo, "--sdk", "wheel", "Release") == 0
    assert not any("resolve" in call for call in fake.calls)
    assert any(call[-3:] == ["fetch", "--build-type", "Release"] for call in fake.calls)
    assert "out/make/wheels" in fake.calls[-1]
    fake.calls.clear()
    assert cli(repo, "test", HOLDER_CORE_REF="v1.2.3") == 0
    assert any("resolve" in call for call in fake.calls)


def test_prepared_sdk_and_conflicting_flags(repo: Path, fake: FakeCommands) -> None:
    sdk = repo / "sdk"
    sdk.mkdir()
    (sdk / "libholder-manifest.json").write_text("{}")
    assert cli(repo, "build", HOLDER_CORE_SDK="sdk") == 0
    assert not any("resolve" in call or "fetch" in call for call in fake.calls)
    assert "--config-settings=cmake.define.HOLDER_KIT_CORE_SOURCE=" in fake.calls[-1]
    fake.calls.clear()
    assert cli(repo, "--sdk", HOLDER_KIT_CORE_SOURCE="core") == 2
    assert not fake.calls


def test_setup_core_is_pinned_atomic_and_idempotent(repo: Path, fake: FakeCommands) -> None:
    assert cli(repo, "setup-core") == 0
    managed = repo / "build/deps/holder-core"
    assert (managed / ".revision").read_text() == PIN
    fetch = next(call for call in fake.calls if "fetch" in call)
    assert fetch[-4:] == ["fetch", "--depth=1", "origin", PIN]
    assert not (repo / ".venv").exists()
    fake.calls.clear()
    assert cli(repo, "setup-core") == 0
    assert not any("fetch" in call or "checkout" in call for call in fake.calls)
    (managed / ".dirty").touch()
    assert cli(repo, "setup-core") == 2
    assert (managed / ".dirty").exists()


def test_failed_core_fetch_leaves_no_partial_checkout(repo: Path, fake: FakeCommands) -> None:
    fake.failure = "fetch"
    assert cli(repo, "setup-core") == 7
    assert list((repo / "build/deps").iterdir()) == []


def test_setup_core_refuses_symlink(repo: Path, fake: FakeCommands, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (repo / "build").symlink_to(outside, target_is_directory=True)
    assert cli(repo, "setup-core") == 2
    assert not fake.calls and list(outside.iterdir()) == []


def test_clean_retains_managed_core_and_refuses_symlinks(repo: Path, fake: FakeCommands) -> None:
    for name in ("build/make", "out/make", "build/deps/holder-core", ".venv", ".core-sdk"):
        (repo / name).mkdir(parents=True)
    assert cli(repo, "clean") == 0
    assert not (repo / "build/make").exists()
    assert all((repo / name).exists() for name in ("build/deps/holder-core", ".venv", ".core-sdk"))
    (repo / "build/make").symlink_to(repo / "build/deps", target_is_directory=True)
    assert cli(repo, "clean") == 2


@pytest.mark.parametrize("system", ["Linux", "Darwin", "FreeBSD", "OpenBSD", "NetBSD", "DragonFly"])
def test_portable_source_route(repo: Path, fake: FakeCommands, monkeypatch: pytest.MonkeyPatch, system: str) -> None:
    monkeypatch.setattr(platform, "system", lambda: system)
    create_core(repo.parent / "holder-core")
    brew = repo / "homebrew"
    (brew / "opt/openssl@3").mkdir(parents=True)
    assert cli(repo, "build") == 0
    assert not any("fetch" in call for call in fake.calls)
    if system == "Darwin":
        assert str(brew / "opt/openssl@3") in fake.envs[-1]["CMAKE_PREFIX_PATH"]


def test_launcher_from_another_directory(repo: Path) -> None:
    env = os.environ.copy()
    env["HOLDER_KIT"] = sys.executable
    result = subprocess.run(
        ["bash", str(repo / "make.sh"), "--help"], cwd=repo.parent,
        env=env, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0 and "setup-core" in result.stdout
    assert not (repo / ".venv").exists()
