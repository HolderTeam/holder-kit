"""Exercise the developer CLI without downloading SDKs or compiling core."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "checkout with spaces"
    repo.mkdir()
    shutil.copyfile(Path(__file__).parents[1] / "make.sh", repo / "make.sh")
    fake_python = repo / "fake-python"
    fake_python.write_text(
        f"#!{sys.executable}\n" + '''
import json
import os
import shutil
import sys
from pathlib import Path

args = sys.argv[1:]
with open("calls.jsonl", "a") as output:
    output.write(json.dumps(args) + "\\n")
if args[:2] == ["-m", "venv"]:
    executable = Path(args[2]) / "bin" / "python"
    executable.parent.mkdir(parents=True)
    shutil.copyfile(__file__, executable)
    executable.chmod(0o755)
elif args[:2] == ["scripts/core-sdk.py", "resolve"]:
    Path("out").mkdir(exist_ok=True)
    Path("out/core-selection.json").write_text("{}")
elif args[:2] == ["scripts/core-sdk.py", "fetch"]:
    sdk = Path("prepared sdk").resolve()
    sdk.mkdir(exist_ok=True)
    (sdk / "libholder-manifest.json").write_text("{}")
    print(sdk)
elif args[:2] == ["-m", os.environ.get("MAKE_TEST_FAIL_MODULE")]:
    sys.exit(7)
''',
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    return repo


def run_make(repo: Path, *args: str, **settings: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    for name in (
        "BUILD_TYPE", "HOLDER_PYTHON_VENV", "HOLDER_PYTHON_CORE_SOURCE",
        "HOLDER_CORE_SDK", "HOLDER_CORE_REF", "MAKE_TEST_FAIL_MODULE",
    ):
        environment.pop(name, None)
    environment.update(HOLDER_PYTHON=str(repo / "fake-python"), **settings)
    return subprocess.run(
        ["bash", str(repo / "make.sh"), *args], cwd=repo.parent,
        env=environment, capture_output=True, text=True, check=False,
    )


def calls(repo: Path) -> list[list[str]]:
    return [json.loads(line) for line in (repo / "calls.jsonl").read_text().splitlines()]


@pytest.mark.parametrize("argument", ["help", "--help", "-h", "unknown"])
def test_help_and_invalid_command_have_no_setup_side_effects(make_repo: Path, argument: str) -> None:
    result = run_make(make_repo, argument)
    assert result.returncode == (2 if argument == "unknown" else 0)
    assert "Usage:" in result.stdout + result.stderr
    assert not (make_repo / "calls.jsonl").exists()
    assert not (make_repo / ".venv").exists()


def test_default_sets_up_venv_and_sdk_then_tests(make_repo: Path) -> None:
    result = run_make(make_repo)
    assert result.returncode == 0, result.stderr
    invoked = calls(make_repo)
    assert invoked[0] == ["-m", "venv", ".venv"]
    assert invoked[1] == ["scripts/core-sdk.py", "resolve"]
    assert invoked[2] == ["scripts/core-sdk.py", "fetch", "--build-type", "RelWithDebInfo"]
    assert invoked[3][:4] == ["-m", "pip", "install", "-e"]
    assert ".[test]" in invoked[3]
    assert invoked[4] == ["-m", "pytest"]
    # The next build reuses its venv and saved selection, but revalidates the SDK.
    result = run_make(make_repo, "test", "-k", "connections or graph")
    assert result.returncode == 0, result.stderr
    assert calls(make_repo)[5][:2] == ["scripts/core-sdk.py", "fetch"]
    assert calls(make_repo)[-1] == ["-m", "pytest", "-k", "connections or graph"]


def test_source_build_and_test_failure_stop_check(make_repo: Path) -> None:
    source = make_repo / "core source"
    source.mkdir()
    (source / "CMakeLists.txt").touch()
    result = run_make(
        make_repo, "check", "Debug", HOLDER_PYTHON_CORE_SOURCE="core source",
        MAKE_TEST_FAIL_MODULE="pytest",
    )
    assert result.returncode == 7
    invoked = calls(make_repo)
    assert not any("scripts/core-sdk.py" in invocation for invocation in invoked)
    assert f"--config-settings=cmake.define.HOLDER_PYTHON_CORE_SOURCE={source}" in invoked[1]
    assert "--config-settings=cmake.build-type=Debug" in invoked[1]
    assert invoked[-1] == ["-m", "pytest"]
    assert not any("mypy" in invocation for invocation in invoked)


def test_sdk_pin_and_release_wheel(make_repo: Path) -> None:
    result = run_make(make_repo, "sdk", "v1.2.3")
    assert result.returncode == 0, result.stderr
    assert calls(make_repo)[1] == ["scripts/core-sdk.py", "resolve", "--core-ref", "v1.2.3"]
    result = run_make(make_repo, "wheel", "Release")
    assert result.returncode == 0, result.stderr
    assert calls(make_repo)[-2] == ["scripts/core-sdk.py", "fetch", "--build-type", "Release"]
    assert calls(make_repo)[-1][:4] == ["-m", "pip", "wheel", "--no-deps"]
    assert "out/make/wheels" in calls(make_repo)[-1]


def test_examples_typecheck_and_missing_venv(make_repo: Path) -> None:
    result = run_make(make_repo, "examples", "graph")
    assert result.returncode == 2
    assert "setup first" in result.stderr
    assert run_make(make_repo, "setup").returncode == 0
    assert run_make(make_repo, "examples", "graph").returncode == 0
    assert calls(make_repo)[-1] == ["examples/graph_analysis.py"]
    assert run_make(make_repo, "typecheck", "--show-error-codes").returncode == 0
    assert calls(make_repo)[-1] == ["-m", "mypy", "--show-error-codes"]


def test_clean_retains_other_outputs_and_refuses_symlinks(make_repo: Path) -> None:
    for name in ("build/make", "out/make", "build/other", ".venv", ".core-sdk"):
        (make_repo / name).mkdir(parents=True)
    result = run_make(make_repo, "clean")
    assert result.returncode == 0, result.stderr
    assert not (make_repo / "build/make").exists()
    assert not (make_repo / "out/make").exists()
    assert all((make_repo / name).exists() for name in ("build/other", ".venv", ".core-sdk"))
    (make_repo / "build/make").symlink_to(make_repo / "build/other", target_is_directory=True)
    assert run_make(make_repo, "clean").returncode == 2
    assert (make_repo / "build/other").exists()
