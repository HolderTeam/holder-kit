"""Managed private checkouts; durable data reconstruction remains in libholder."""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit
from uuid import uuid4

if TYPE_CHECKING:
    from . import Context
    from .data import Project

_MARKER = ".holder-kit.json"


@dataclass(frozen=True, slots=True)
class Workspace:
    """One private project and its context. Closing retains all local edits.

    Project, source, ref and revision describe initialization, not a live view of
    subsequent commits. Use context for the existing entity and analysis APIs.
    """

    path: Path
    context: Context
    project: Project
    source: str | None
    ref: str | None
    revision: str

    @property
    def closed(self) -> bool:
        return self.context.closed

    def close(self) -> None:
        self.context.close()

    def __enter__(self) -> Workspace:
        if self.closed:
            raise RuntimeError("Holder workspace is closed")
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def _default_parent() -> Path:
    if value := os.environ.get("HOLDER_KIT_WORKSPACES"):
        return Path(value).expanduser()
    if sys.platform == "win32":
        return (
            Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
            / "HolderKit/workspaces"
        )
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/HolderKit/workspaces"
    return (
        Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
        / "holder-kit/workspaces"
    )


def _destination(workspace: os.PathLike[str] | str | None) -> Path:
    path = (
        Path(workspace).expanduser()
        if workspace is not None
        else _default_parent() / str(uuid4())
    )
    if path.is_symlink():
        raise ValueError("Workspace destination must not be a symlink")
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Never adopt an existing directory, even if empty.
    path.mkdir(mode=0o700)
    return path


def _remote(remote_url: str) -> str:
    if not isinstance(remote_url, str):
        raise TypeError("remote_url must be a string")
    if (
        not remote_url
        or "::" in remote_url
        or any(ord(c) < 33 or ord(c) == 127 for c in remote_url)
    ):
        raise ValueError("An explicit Git remote URL is required")
    if "://" in remote_url:
        parsed = urlsplit(remote_url)
        if (
            parsed.scheme not in {"https", "ssh", "git"}
            or not parsed.hostname
            or not parsed.path
        ):
            raise ValueError(
                "Use an HTTPS, SSH or git:// remote; local paths are unsupported"
            )
        if (
            parsed.password
            or parsed.query
            or parsed.fragment
            or (parsed.username and parsed.scheme != "ssh")
        ):
            raise ValueError(
                "Do not embed credentials, query parameters or fragments in remote URLs"
            )
        if parsed.hostname.startswith("-") or (
            parsed.username
            and not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", parsed.username)
        ):
            raise ValueError("Unsupported SSH user or host")
    elif not re.fullmatch(
        r"(?:[A-Za-z0-9_][A-Za-z0-9_.-]*@)?[A-Za-z0-9][A-Za-z0-9.-]*:[^\\]+", remote_url
    ):
        raise ValueError(
            "Use an explicit Git remote; local paths and helper transports are unsupported"
        )
    elif re.match(r"^[A-Za-z]:", remote_url):
        raise ValueError("Local paths are unsupported")
    return remote_url


def _git(*args: str, network: bool = False) -> bytes:
    env = os.environ.copy()
    for key in tuple(env):
        if key.startswith("GIT_") and key not in {
            "GIT_SSH",
            "GIT_SSH_COMMAND",
            "GIT_ASKPASS",
        }:
            env.pop(key)
    env["GIT_TERMINAL_PROMPT"] = "0"
    # Network clone can use configured credential helpers and SSH credentials.
    # Checkout ignores host filters, attributes and templates; project-supplied
    # hooks must never execute. No submodule initialization is performed.
    if not network:
        env["GIT_CONFIG_NOSYSTEM"] = "1"
        env["GIT_CONFIG_GLOBAL"] = os.devnull
    try:
        result = subprocess.run(
            [
                "git",
                "-c",
                f"core.hooksPath={os.devnull}",
                "-c",
                f"core.attributesFile={os.devnull}",
                "-c",
                "protocol.file.allow=never",
                "-c",
                "protocol.ext.allow=never",
                *args,
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError:
        raise RuntimeError(
            "Git is required for managed Holder Kit workspaces"
        ) from None
    if result.returncode:
        # Git diagnostics can contain URLs, helper output and credentials.
        raise RuntimeError(
            "Git operation failed; check the remote, ref and Git credential setup"
        )
    return result.stdout


def _private_tree(path: Path) -> None:
    for directory, names, files in os.walk(path, followlinks=False):
        for name in names + files:
            item = Path(directory) / name
            mode = item.lstat()
            if stat.S_ISLNK(mode.st_mode):
                raise ValueError("Managed workspaces do not support symlinks")
            if not (stat.S_ISDIR(mode.st_mode) or stat.S_ISREG(mode.st_mode)):
                raise ValueError(
                    "Managed workspaces require ordinary files and directories"
                )
            if stat.S_ISREG(mode.st_mode) and mode.st_nlink != 1:
                raise ValueError(
                    "Managed workspaces do not support shared hard-linked files"
                )


def _checkout_safe(root: Path) -> None:
    if not (root / ".git").is_dir():
        raise ValueError("A standalone project Git checkout is required")
    for relative in (".git/commondir", ".git/objects/info/alternates"):
        if (root / relative).exists():
            raise ValueError("Shared Git object stores and worktrees are unsupported")
    top = Path(
        os.fsdecode(_git("-C", str(root), "rev-parse", "--show-toplevel")).strip()
    )
    if top.resolve() != root:
        raise ValueError("Git working tree escapes the private checkout")
    # Do not read project secrets or attempt keyring access for encrypted copies.
    bootstrap = root / ".holder/privacy.json"
    if not bootstrap.is_file() or not (root / ".holder/project.json").is_file():
        raise ValueError("A durable Holder project manifest is required")
    privacy = json.loads(bootstrap.read_text(encoding="utf-8"))
    if not isinstance(privacy, dict) or privacy.get("mode") != "plain":
        raise ValueError("Managed workspaces currently support plain projects only")
    if (root / "server").exists():
        raise ValueError("Project checkouts must not contain daemon server state")


def _finish(
    path: Path, context: Context, project: Project, source: str | None, ref: str | None
) -> Workspace:
    root = Path(project.root_path)
    relative = root.relative_to(path).as_posix()
    _private_tree(path)
    _checkout_safe(root)
    revision = _git("-C", str(root), "rev-parse", "HEAD").decode("ascii").strip()
    marker = {
        "version": 1,
        "state": "ready",
        "project_path": relative,
        "project_id": project.project_id,
        "source": source,
        "ref": ref,
        "revision": revision,
    }
    temporary = path / (_MARKER + ".tmp")
    temporary.write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path / _MARKER)
    return Workspace(path, context, project, source, ref, revision)


def create(name: str, *, workspace: os.PathLike[str] | str | None = None) -> Workspace:
    """Create one fresh private project. An existing destination is never reused."""
    from . import Context

    if not isinstance(name, str):
        raise TypeError("name must be a string")
    if not name.strip() or "\0" in name:
        raise ValueError("A nonempty project name is required")
    path = _destination(workspace)
    context = None
    try:
        context = Context(path / "data")
        project = context.create_project(name)
        return _finish(path, context, project, None, None)
    except BaseException:
        if context is not None:
            context.close()
        shutil.rmtree(path)
        raise


def clone(
    remote_url: str,
    *,
    workspace: os.PathLike[str] | str | None = None,
    ref: str | None = None,
) -> Workspace:
    """Clone committed remote data into a private checkout and reconstructed DB.

    ref may be a branch, tag or commit available in the clone. No pull/reset or
    reuse is implicit. Local paths, encrypted projects and submodules are unsupported.
    """
    from . import Context, _native
    from .data import Project

    source = _remote(remote_url)
    if not _native.PROJECT_IMPORT_SUPPORTED:
        raise NotImplementedError(
            "Clone requires a core build with explicit project import support"
        )
    if ref is not None and (
        not isinstance(ref, str)
        or not ref
        or ref.startswith("-")
        or any(ord(c) < 33 for c in ref)
    ):
        raise ValueError("ref must be a nonempty branch, tag or commit")
    path = _destination(workspace)
    context = None
    try:
        # Establish our own empty context before any durable project appears.
        # Fresh import must not masquerade as recovery of a lost database.
        context = Context(path / "data")
        root = path / "data/projects/project"
        root.parent.mkdir(parents=True)
        _git(
            "clone",
            "--no-checkout",
            "--no-local",
            "--no-hardlinks",
            "--template=",
            "--",
            source,
            str(root),
            network=True,
        )
        try:
            selected = (
                _git(
                    "-C",
                    str(root),
                    "rev-parse",
                    "--verify",
                    "--end-of-options",
                    (ref or "HEAD") + "^{commit}",
                )
                .decode("ascii")
                .strip()
            )
        except RuntimeError:
            if ref is None:
                raise
            selected = (
                _git(
                    "-C",
                    str(root),
                    "rev-parse",
                    "--verify",
                    "--end-of-options",
                    "refs/remotes/origin/" + ref + "^{commit}",
                )
                .decode("ascii")
                .strip()
            )
        tree = _git("-C", str(root), "ls-tree", "-r", "-z", selected)
        for entry in tree.split(b"\0"):
            if not entry:
                continue
            info, name = entry.split(b"\t", 1)
            if info.split(b" ", 1)[0] not in {b"100644", b"100755"}:
                raise ValueError("Clone does not support symlinks or submodules")
            parts = PurePosixPath(os.fsdecode(name)).parts
            if any(
                part.lower()
                in {".git", "server", "holder.db", "holder.db-wal", "holder.db-shm"}
                or "\\" in part
                or ":" in part
                for part in parts
            ):
                raise ValueError(
                    "Clone contains unsupported storage paths or server state"
                )
        _git("-C", str(root), "checkout", "--detach", selected)
        _private_tree(path)
        _checkout_safe(root)
        project = Project._from_native(context._context.import_project(str(root)))
        if Path(project.root_path) != root:
            raise ValueError("Clone must reconstruct exactly one private project")
        return _finish(path, context, project, source, ref)
    except BaseException:
        if context is not None:
            context.close()
        shutil.rmtree(path)
        raise


def reopen(workspace: os.PathLike[str] | str) -> Workspace:
    """Reopen a completed Kit workspace without cloning or resetting its edits."""
    from . import Context

    path = Path(workspace).expanduser()
    if path.is_symlink():
        raise ValueError("Workspace must not be a symlink")
    path = path.resolve(strict=True)
    _private_tree(path)
    marker_path = path / _MARKER
    if not marker_path.is_file():
        raise ValueError("Not a completed Holder Kit workspace")
    marker: dict[str, Any] = json.loads(marker_path.read_text(encoding="utf-8"))
    if (
        not isinstance(marker, dict)
        or marker.get("version") != 1
        or marker.get("state") != "ready"
    ):
        raise ValueError("Unsupported or incomplete Holder Kit workspace")
    relative = marker.get("project_path")
    if not isinstance(relative, str):
        raise ValueError("Invalid workspace project path")
    parts = PurePosixPath(relative).parts
    if (
        len(parts) != 3
        or parts[:2] != ("data", "projects")
        or parts[2] in {".", ".."}
        or "\\" in relative
        or ":" in relative
    ):
        raise ValueError("Invalid workspace project path")
    root = path / relative
    if not root.is_dir() or list((path / "data/projects").iterdir()) != [root]:
        raise ValueError("Workspace must contain exactly its recorded project")
    _checkout_safe(root)
    source, ref, revision = (
        marker.get("source"),
        marker.get("ref"),
        marker.get("revision"),
    )
    if source is not None:
        _remote(source)
    if (
        (ref is not None and not isinstance(ref, str))
        or not isinstance(revision, str)
        or not re.fullmatch(r"[0-9a-f]{40}", revision)
    ):
        raise ValueError("Invalid workspace source revision")
    context = Context(path / "data")
    try:
        projects = context.list_projects()
        if (
            len(projects) != 1
            or projects[0].project_id != marker.get("project_id")
            or Path(projects[0].root_path) != root
        ):
            raise ValueError("Workspace database does not match its private project")
        return Workspace(path, context, projects[0], source, ref, revision)
    except BaseException:
        context.close()
        raise


__all__ = ["Workspace", "create", "clone", "reopen"]
