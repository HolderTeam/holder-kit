"""Explicit publication and disposal of Kit-managed projects."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from ._storage import _MARKER, _git, _managed_marker, _remote, _remove_tree
from .data import DiscardPreview, Project, PushPreview, PushResult


def _validated(project: Project) -> tuple[Path, Path, dict[str, Any]]:
    path = project.path
    if path.resolve(strict=True) != path:
        raise ValueError("Managed project path was replaced or redirected")
    path, root, marker = _managed_marker(path)
    if marker.get("project_id") != project.project_id:
        raise ValueError("Managed storage belongs to a different project")
    if not project.closed and Path(project.root_path) != root:
        raise ValueError("Managed storage does not match the live project")
    publications = marker.get("publications", [])
    if not isinstance(publications, list):
        raise ValueError("Invalid publication records")
    for record in publications:
        if not isinstance(record, dict) or not all(
            isinstance(record.get(key), str) for key in ("remote_url", "branch", "revision")
        ):
            raise ValueError("Invalid publication record")
        _remote(record["remote_url"])
        _branch(record["branch"])
        _revision(record["revision"])
    return path, root, marker


def _revision(value: str) -> None:
    import re

    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError("Invalid publication revision")


def _branch(branch: str) -> str:
    if not isinstance(branch, str):
        raise TypeError("branch must be a string")
    if not branch or branch.startswith(("-", "refs/")) or branch == "HEAD":
        raise ValueError("An explicit branch name is required")
    try:
        _git("check-ref-format", "refs/heads/" + branch)
    except RuntimeError:
        raise ValueError("Invalid branch name") from None
    return "refs/heads/" + branch


def _save(path: Path, marker: dict[str, Any]) -> None:
    temporary = path / (_MARKER + ".tmp")
    temporary.write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path / _MARKER)


def _target(
    project: Project, branch: str, remote_url: str | None,
) -> tuple[PushPreview, Path, dict[str, Any], bool]:
    project._live_context()
    ref = _branch(branch)
    destination = remote_url if remote_url is not None else project.remote_url
    if destination is None:
        raise ValueError("A new project needs an explicit remote_url")
    destination = _remote(destination)
    path, root, marker = _validated(project)
    revision = project.revision
    advertised = _git("-C", str(root), "ls-remote", "--symref", "--", destination,
                      "HEAD", ref, network=True)
    remote_revision = None
    for line in advertised.decode("utf-8").splitlines():
        value, name = line.split("\t", 1)
        if name == "HEAD" and value == "ref: " + ref:
            raise ValueError("Publication cannot update the remote default branch")
        if name == ref:
            remote_revision = value
    previous = next((record for record in marker.get("publications", [])
                     if record["remote_url"] == destination and record["branch"] == branch), None)
    attempt = marker.get("publication_attempt")
    recovered = attempt == {"remote_url": destination, "branch": branch, "revision": revision} and remote_revision == revision
    if remote_revision is not None and previous is None and not recovered:
        raise ValueError("First publication requires a new remote branch")
    if remote_revision is not None and previous is not None:
        # An unknown remote commit cannot be an ancestor of our local HEAD.
        ancestors = _git("-C", str(root), "rev-list", revision).decode("ascii").splitlines()
        if remote_revision not in ancestors:
            raise ValueError("Remote branch has diverged; publication must be fast-forward")
    dirty = bool(_git("-C", str(root), "status", "--porcelain", "-z"))
    return PushPreview(destination, branch, revision, remote_revision is None, dirty), path, marker, recovered


def preview_push(project: Project, *, branch: str, remote_url: str | None) -> PushPreview:
    return _target(project, branch, remote_url)[0]


def push(
    project: Project, *, branch: str, remote_url: str | None,
    expected_revision: str | None,
) -> PushResult:
    preview, path, marker, recovered = _target(project, branch, remote_url)
    if expected_revision is not None and expected_revision != preview.revision:
        raise ValueError("Project changed since the reviewed revision")
    record = {"remote_url": preview.remote_url, "branch": branch, "revision": preview.revision}
    if not recovered:
        # An interrupted push may have succeeded remotely. Retain the exact
        # attempt so retry can recognize that commit, without adopting any other
        # pre-existing branch. This is not a record of successful publication.
        marker["publication_attempt"] = record
        _save(path, marker)
        ref = "refs/heads/" + branch
        options = ["--force-with-lease=" + ref + ":"] if preview.new_branch else []
        try:
            _git("-C", project.root_path, "-c", "push.followTags=false",
                 "push", "--porcelain", "--no-verify", "--recurse-submodules=no",
                 *options, "--", preview.remote_url, preview.revision + ":" + ref,
                 network=True)
        except RuntimeError:
            raise RuntimeError(
                "Publication failed or its outcome is unknown; local work is retained. "
                "Check credentials, connectivity and the remote branch before retrying."
            ) from None
    publications = [entry for entry in marker.get("publications", [])
                    if (entry["remote_url"], entry["branch"]) != (preview.remote_url, branch)]
    publications.append(record)
    marker["publications"] = publications
    marker.pop("publication_attempt", None)
    try:
        _save(path, marker)
    except OSError:
        raise RuntimeError("Push succeeded, but its local record could not be saved; retry this revision") from None
    return PushResult(preview.remote_url, branch, preview.revision)


def preview_discard(project: Project) -> DiscardPreview:
    path, root, marker = _validated(project)
    revision = _git("-C", str(root), "rev-parse", "HEAD").decode("ascii").strip()
    published = [record["revision"] for record in marker.get("publications", [])]
    # These records describe confirmed pushes, not current remote retention.
    unpublished = bool(_git("-C", str(root), "rev-list", revision, "--not", *published))
    dirty = bool(_git("-C", str(root), "status", "--porcelain", "-z"))
    warnings = ["Permanently removes this local project, its database and any local artifacts. "
                "Publication does not back up all local files."]
    if unpublished:
        warnings.append("Local commits have not been recorded as published by Kit.")
    if dirty:
        warnings.append("Uncommitted or untracked project files will be lost.")
    return DiscardPreview(path, revision, unpublished, dirty, tuple(warnings))


def discard(project: Project, *, confirm: bool) -> None:
    if confirm is not True:
        raise ValueError("Permanent disposal requires confirm=True; review preview_discard() first")
    path, _, _ = _validated(project)
    project.close()
    # Move the validated directory aside first. A stale handle cannot delete a
    # new project later created at the original location. On partial cleanup,
    # report the remaining directory so callers can inspect it deliberately.
    removed = path.with_name(".holder-kit-discard-" + str(uuid4()))
    path.rename(removed)
    try:
        _remove_tree(removed)
    except OSError as error:
        raise RuntimeError(f"Project is closed; incomplete permanent cleanup remains at {removed}") from error
