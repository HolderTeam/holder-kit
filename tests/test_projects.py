from __future__ import annotations

import json
import shlex
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import pytest

import holderkit


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), *args], text=True, stderr=subprocess.PIPE
    ).strip()


def test_project_properties_read_current_state_and_records_are_detached(
    tmp_path: Path,
) -> None:
    with holderkit.create("Original", workspace=tmp_path / "private") as project:
        assert isinstance(project, holderkit.Project)
        assert not hasattr(project, "context")
        assert not hasattr(project, "project")
        original = project.to_record()
        # Simulate another Holder writer updating the projection. Production
        # reads must continue through Core, rather than retaining opening values.
        with sqlite3.connect(project.path / "data/server/holder.db") as database:
            database.execute(
                "UPDATE projects SET name = ?, updated_at = ?, git_provider = ? WHERE project_id = ?",
                ("Renamed", original["updated_at"] + 10, "example", project.project_id),
            )
        assert project.name == "Renamed"
        assert project.updated_at == original["updated_at"] + 10
        assert project.git_provider == "example"
        assert project.to_record()["name"] == "Renamed"
        assert original["name"] == "Original"
        assert original["git_provider"] is None
        assert project.created_datetime.tzinfo is not None
        before = project.revision
        card = project.create_card("Observation", "Body")
        assert project.revision != before
        project.update_card(card.card_id, "Changed")
        after = project.revision
        path = project.path
        identity = project.project_id
    assert project.closed and project.path == path and project.project_id == identity
    assert git(Path(original["root_path"]), "rev-parse", "HEAD") == after
    with pytest.raises(RuntimeError, match="closed"):
        project.name
    with pytest.raises(RuntimeError, match="closed"):
        project.to_record()
    with pytest.raises(RuntimeError, match="closed"):
        project.revision


def test_project_operations_are_scoped_in_a_shared_context(tmp_path: Path) -> None:
    with holderkit.open(tmp_path / "shared") as context:
        first = context.create_project("First")
        second = context.create_project("Second")
        a = first.create_card("One", "First body")
        b = second.create_card("Two", "Second body")
        first.tags.add(a.card_id, "science")
        second.tags.add(b.card_id, "other")
        second_body = second.get_card_content(b.card_id)
        milestone = first.milestones.add(a.card_id, 100)[0]
        first.milestones.update(
            a.card_id, milestone["milestone_id"], {"description": "Review"}
        )
        assert first.milestones.in_range(0, 200)[0]["description"] == "Review"
        assert [card.card_id for card in first.list_cards()] == [a.card_id]
        assert first.cards.to_records()[0]["project_id"] == first.project_id
        assert first.tags.cards_with_tag("science")[0]["card_id"] == a.card_id
        assert first.tags.project_counts()[0]["count"] == 1
        assert len(first.milestones.to_records()) == 1
        # Core allows an outgoing connection to a card in another project.
        first.connections.add(a.card_id, b.card_id, "related")
        assert first.connections.to_records()[0]["to_card_id"] == b.card_id
        tables = first.to_dataframes(include_content=True)
        graph = first.to_networkx(include_content=True)
        assert tables["projects"]["name"].tolist() == ["First"]
        assert tables["cards"]["card_id"].tolist() == [a.card_id]
        assert tables["tags"]["tag"].tolist() == ["science"]
        assert first.cards.to_dataframe().shape[0] == 1
        assert first.connections.to_dataframe().shape[0] == 1
        assert first.tags.to_dataframe().shape[0] == 1
        assert first.milestones.to_dataframe().shape[0] == 1
        assert graph.has_edge(a.card_id, b.card_id)
        for operation in (
            lambda: first.get_card_content(b.card_id),
            lambda: first.update_card(b.card_id, "Wrong project"),
            lambda: first.create_card("Child", parent_card_id=b.card_id),
            lambda: first.tags.add(b.card_id, "Wrong project"),
            lambda: first.tags.remove(b.card_id, "other"),
            lambda: first.tags.list(b.card_id),
            lambda: first.tags.list_editable(b.card_id),
            lambda: first.milestones.add(b.card_id, 200),
            lambda: first.milestones.list(b.card_id),
            lambda: first.milestones.remove(b.card_id, milestone["milestone_id"]),
            lambda: first.milestones.update(
                b.card_id, milestone["milestone_id"], {"description": "Wrong"}
            ),
            lambda: first.connections.add(b.card_id, a.card_id, "related"),
            lambda: first.connections.remove(b.card_id, a.card_id, "related"),
        ):
            with pytest.raises(ValueError, match="belong"):
                operation()
        assert second.get_card_content(b.card_id) == second_body
        first.connections.remove(a.card_id, b.card_id, "related")
        first.milestones.remove(a.card_id, milestone["milestone_id"])
        first.tags.remove(a.card_id, "science")
        assert first.connections.to_records() == []
        assert first.milestones.to_records() == []
        assert first.tags.to_records() == []
    assert tables["cards"].shape[0] == 1 and graph.number_of_edges() == 1


def test_borrowed_projects_close_without_closing_the_context(tmp_path: Path) -> None:
    with holderkit.open(tmp_path / "shared") as context:
        first = context.create_project("First")
        second = context.create_project("Second")
        collection = first.cards
        with first:
            first.create_card("Card")
        assert first.closed and not context.closed and not second.closed
        with pytest.raises(RuntimeError, match="closed"):
            collection.to_records()
        second.create_card("Still usable")
        reopened_handle = context.list_projects()[0]
        assert not reopened_handle.closed
        assert len(context.projects.to_records()) == 2
    assert second.closed and reopened_handle.closed


def test_managed_project_keeps_native_context_alive(tmp_path: Path) -> None:
    import gc

    project = holderkit.create("Lifetime", workspace=tmp_path / "private")
    cards = project.cards
    identity = project.project_id
    del project
    gc.collect()
    assert cards.to_records() == []
    cards._project.close()
    with holderkit.reopen(tmp_path / "private") as reopened:
        assert reopened.project_id == identity


@dataclass
class Remote:
    url: str
    source: Path
    bare: Path
    project_id: str
    card_id: str
    other_id: str
    revision: str


@pytest.fixture
def remote(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Remote]:
    if not holderkit._native.PROJECT_IMPORT_SUPPORTED:
        pytest.skip(
            "Remote import needs the newer core API; use an explicit development source override"
        )
    # Bound every Git client used by these disposable remotes, including Kit's
    # subprocess calls. A stalled fixture must fail with the command identified
    # rather than occupying a runner until the entire workflow times out.
    original_run = subprocess.run

    def bounded_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        kwargs.setdefault("timeout", 30)
        return original_run(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", bounded_run)
    with holderkit.open(tmp_path / "source") as context:
        project = context.create_project("Remote research")
        first = context.create_card(
            project.project_id, "Evidence", "Original body #science"
        )
        second = context.create_card(project.project_id, "Question", "Other body")
        context.connections.add(first.card_id, second.card_id, "related")
        context.milestones.add(first.card_id, 100, description="Review")
        source = Path(project.root_path)
    bare = tmp_path / "research.git"
    subprocess.run(
        ["git", "clone", "--bare", str(source), str(bare)],
        check=True,
        capture_output=True,
    )
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    daemon = subprocess.Popen(
        [
            "git",
            "daemon",
            "--reuseaddr",
            "--export-all",
            "--enable=receive-pack",
            "--listen=127.0.0.1",
            f"--port={port}",
            f"--base-path={tmp_path}",
            str(tmp_path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        for _ in range(100):
            if daemon.poll() is not None:
                raise RuntimeError("Fixture Git daemon failed to start")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    break
            except OSError:
                time.sleep(0.02)
        else:
            raise RuntimeError("Fixture Git daemon did not become ready")
        yield Remote(
            f"git://127.0.0.1:{port}/research.git",
            source,
            bare,
            project.project_id,
            first.card_id,
            second.card_id,
            git(source, "rev-parse", "HEAD"),
        )
    finally:
        daemon.terminate()
        daemon.communicate(timeout=5)


def test_push_new_project_then_repeat_after_reopen(remote: Remote, tmp_path: Path) -> None:
    path = tmp_path / "experiment"
    project = holderkit.create("Experiment", workspace=path)
    card = project.create_card("Evidence", "Experiment body")
    root = Path(project.root_path)
    (root / "notebook.ipynb").write_text("untracked analysis")
    before = project.revision
    with pytest.raises(ValueError, match="remote_url"):
        project.push(branch="analysis/result")
    preview = project.preview_push(branch="analysis/result", remote_url=remote.url)
    assert preview.new_branch and preview.has_uncommitted_changes
    assert preview.revision == before
    assert not git(remote.bare, "branch", "--list", "analysis/result")
    result = project.push(branch=preview.branch, remote_url=preview.remote_url,
                          expected_revision=preview.revision)
    assert isinstance(result, holderkit.PushResult)
    assert result.revision == before
    assert not project.closed and project.remote_url is None
    assert git(remote.bare, "rev-parse", "refs/heads/analysis/result") == before
    assert git(remote.bare, "rev-parse", "HEAD") == remote.revision
    tree = git(remote.bare, "ls-tree", "-r", "--name-only", before)
    assert "notebook.ipynb" not in tree and "holder.db" not in tree and ".holder-kit" not in tree
    project.close()
    project = holderkit.reopen(path)
    assert not project.preview_push(branch=result.branch, remote_url=remote.url).new_branch
    assert not project.preview_discard().has_unpublished_commits
    assert project.preview_discard().has_uncommitted_changes
    project.update_card(card.card_id, "Next experiment")
    assert project.preview_discard().has_unpublished_commits
    with pytest.raises(ValueError, match="reviewed revision"):
        project.push(branch=result.branch, remote_url=remote.url, expected_revision=before)
    next_result = project.push(branch=result.branch, remote_url=remote.url)
    assert next_result.revision != result.revision
    assert git(remote.bare, "rev-parse", "refs/heads/analysis/result") == next_result.revision
    assert git(remote.bare, "rev-parse", "HEAD") == remote.revision
    project.discard(confirm=True)
    assert project.closed and not path.exists()
    assert git(remote.bare, "rev-parse", "refs/heads/analysis/result") == next_result.revision


def test_clone_push_keeps_origin_and_detached_checkout(remote: Remote, tmp_path: Path) -> None:
    with holderkit.clone(remote.url, workspace=tmp_path / "clone") as project:
        project.update_card(remote.card_id, "Proposal")
        root = Path(project.root_path)
        old_head = (root / ".git/HEAD").read_text()
        result = project.push(branch="proposal")
        assert result.remote_url == remote.url
        assert project.remote_url == remote.url
        assert (root / ".git/HEAD").read_text() == old_head
        assert git(remote.bare, "rev-parse", "HEAD") == remote.revision


def test_push_to_another_destination_ignores_hooks_and_tags(remote: Remote, tmp_path: Path) -> None:
    destination = tmp_path / "own.git"
    subprocess.run(["git", "init", "--bare", str(destination)], check=True, capture_output=True)
    url = remote.url.removesuffix("research.git") + "own.git"
    with holderkit.clone(remote.url, workspace=tmp_path / "clone") as project:
        project.update_card(remote.card_id, "Own experiment")
        root = Path(project.root_path)
        # If hooks were enabled this would fail publication.
        hook = root / ".git/hooks/pre-push"
        hook.parent.mkdir(exist_ok=True)
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)
        git(root, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
            "tag", "-a", "private-tag", "-m", "Private tag")
        git(root, "config", "push.followTags", "true")
        result = project.push(branch="own-experiment", remote_url=url)
        assert result.remote_url == url and project.remote_url == remote.url
        assert git(destination, "rev-parse", "refs/heads/own-experiment") == project.revision
        assert git(destination, "tag", "--list") == ""
        assert git(remote.bare, "rev-parse", "HEAD") == remote.revision
        assert git(remote.bare, "branch", "--list", "own-experiment") == ""


def test_push_success_with_local_record_failure_can_be_retried(remote: Remote, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from holderkit import _publication

    with holderkit.clone(remote.url, workspace=tmp_path / "clone") as project:
        original = _publication._save
        saves = 0
        def save(path: Path, marker: dict[str, object]) -> None:
            nonlocal saves
            saves += 1
            if saves == 2:
                raise PermissionError("Fixture record failure")
            original(path, marker)
        monkeypatch.setattr(_publication, "_save", save)
        with pytest.raises(RuntimeError, match="Push succeeded"):
            project.push(branch="retry-record")
        assert not project.closed
        assert git(remote.bare, "rev-parse", "refs/heads/retry-record") == project.revision
        monkeypatch.setattr(_publication, "_save", original)
        assert project.push(branch="retry-record").revision == project.revision


def test_push_failure_does_not_leak_helper_output(remote: Remote, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from holderkit import _publication
    from holderkit._storage import _git as real_git

    with holderkit.clone(remote.url, workspace=tmp_path / "clone") as project:
        def fail(*args: str, network: bool = False) -> bytes:
            if "push" in args:
                raise RuntimeError("Fixture credential secret")
            return real_git(*args, network=network)
        monkeypatch.setattr(_publication, "_git", fail)
        with pytest.raises(RuntimeError, match="credentials") as error:
            project.push(branch="failure")
        assert "secret" not in str(error.value) and error.value.__suppress_context__
        assert project.path.exists() and not project.closed
        assert git(remote.bare, "branch", "--list", "failure") == ""


def test_push_rejects_existing_default_and_diverged_branches(remote: Remote, tmp_path: Path) -> None:
    default = git(remote.bare, "symbolic-ref", "--short", "HEAD")
    git(remote.bare, "branch", "occupied", remote.revision)
    with holderkit.clone(remote.url, workspace=tmp_path / "clone") as project:
        project.update_card(remote.card_id, "Proposal")
        for branch, message in ((default, "default branch"), ("occupied", "new remote branch")):
            with pytest.raises(ValueError, match=message):
                project.push(branch=branch)
        project.push(branch="proposal")
        git(remote.source, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
            "commit", "--allow-empty", "-m", "Divergent source")
        git(remote.source, "push", "--force", str(remote.bare), "HEAD:refs/heads/proposal")
        with pytest.raises(ValueError, match="diverged"):
            project.push(branch="proposal")
        assert not project.closed
        assert project.get_card_content(remote.card_id) == "Proposal"


def test_push_creation_race_and_unknown_outcome(remote: Remote, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from holderkit import _publication

    with holderkit.clone(remote.url, workspace=tmp_path / "clone") as project:
        project.update_card(remote.card_id, "Proposal")
        from holderkit._storage import _git as real_git
        def race(*args: str, network: bool = False) -> bytes:
            if "push" in args:
                git(remote.bare, "branch", "race", remote.revision)
            return real_git(*args, network=network)
        monkeypatch.setattr(_publication, "_git", race)
        with pytest.raises(RuntimeError, match="local work is retained"):
            project.push(branch="race")
        assert git(remote.bare, "rev-parse", "refs/heads/race") == remote.revision
        assert project.get_card_content(remote.card_id) == "Proposal"
        monkeypatch.setattr(_publication, "_git", real_git)
        with pytest.raises(ValueError, match="new remote branch"):
            project.push(branch="race")
        def unknown(*args: str, network: bool = False) -> bytes:
            result = real_git(*args, network=network)
            if "push" in args:
                raise RuntimeError("Network response was lost")
            return result
        monkeypatch.setattr(_publication, "_git", unknown)
        with pytest.raises(RuntimeError, match="outcome is unknown"):
            project.push(branch="recoverable")
        marker = json.loads((project.path / ".holder-kit.json").read_text())
        assert not marker.get("publications")
        monkeypatch.setattr(_publication, "_git", real_git)
        result = project.push(branch="recoverable")
        assert result.revision == project.revision


@pytest.mark.parametrize("branch", ["", "HEAD", "-option", "refs/heads/topic", "bad name", "bad..name", "bad:ref"])
def test_invalid_publication_branch_is_rejected(tmp_path: Path, branch: str) -> None:
    with holderkit.create("Research", workspace=tmp_path / "private") as project:
        with pytest.raises(ValueError, match="branch"):
            project.push(branch=branch, remote_url="git@example.org:research.git")


def test_discard_confirmation_close_and_stale_handles(tmp_path: Path) -> None:
    path = tmp_path / "private"
    project = holderkit.create("Research", workspace=path)
    card = project.create_card("Evidence", "Unsaved remotely")
    (Path(project.root_path) / "analysis.txt").write_text("Local artifact")
    preview = project.preview_discard()
    assert preview.path == path
    assert preview.has_unpublished_commits and preview.has_uncommitted_changes
    assert len(preview.warnings) == 3
    with pytest.raises(ValueError, match="confirm=True"):
        project.discard()
    assert not project.closed and path.exists()
    project.close()
    with holderkit.reopen(path) as reopened:
        assert reopened.get_card_content(card.card_id) == "Unsaved remotely"
    project.discard(confirm=True)
    assert project.closed and not path.exists()
    with pytest.raises(FileNotFoundError):
        project.discard(confirm=True)
    with holderkit.create("Replacement", workspace=path) as replacement:
        with pytest.raises(ValueError, match="different project"):
            project.discard(confirm=True)
        assert replacement.name == "Replacement"


def test_discard_refuses_shared_context_and_tampered_marker(tmp_path: Path) -> None:
    with holderkit.open(tmp_path / "shared") as context:
        first = context.create_project("First")
        second = context.create_project("Second")
        for method in (lambda: first.discard(confirm=True), lambda: first.push(branch="proposal")):
            with pytest.raises(ValueError, match="managed storage|remote_url"):
                method()
        assert not context.closed and second.name == "Second"
    with holderkit.create("Research", workspace=tmp_path / "private") as project:
        marker_path = project.path / ".holder-kit.json"
        marker = json.loads(marker_path.read_text())
        marker["project_path"] = "../../outside"
        marker_path.write_text(json.dumps(marker))
        with pytest.raises(ValueError, match="project path"):
            project.discard(confirm=True)
        assert not project.closed


def test_discard_refuses_symlink_redirect(tmp_path: Path) -> None:
    path = tmp_path / "private"
    project = holderkit.create("Research", workspace=path)
    project.close()
    moved = tmp_path / "moved"
    path.rename(moved)
    try:
        path.symlink_to(moved, target_is_directory=True)
    except OSError:
        pytest.skip("Directory symlinks are unavailable")
    with pytest.raises(ValueError, match="redirected"):
        project.discard(confirm=True)
    assert moved.is_dir()


def test_discard_partial_cleanup_reports_remaining_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from holderkit import _publication

    project = holderkit.create("Research", workspace=tmp_path / "private")
    def fail(path: Path) -> None:
        raise PermissionError("Fixture cleanup failure")
    monkeypatch.setattr(shutil, "rmtree", fail)
    with pytest.raises(RuntimeError, match="incomplete permanent cleanup remains"):
        project.discard(confirm=True)
    assert project.closed and not project.path.exists()
    assert len(list(tmp_path.glob(".holder-kit-discard-*"))) == 1


def test_create_reopen_retains_edits_and_context_lifecycle(tmp_path: Path) -> None:
    path = tmp_path / "private"
    with holderkit.create("Research", workspace=path) as workspace:
        assert workspace.path == path
        assert workspace.remote_url is None
        assert len(workspace.revision) == 40
        card = workspace.create_card("Imported data", "Body")
        initial_revision = workspace.revision
    assert workspace.closed
    assert (path / "data/server/holder.db").is_file()
    with holderkit.reopen(path) as reopened:
        assert reopened.project_id == workspace.project_id
        assert reopened.get_card_content(card.card_id) == "Body"
        assert reopened.revision == initial_revision
        reopened.update_card(card.card_id, "Changed")
    with holderkit.reopen(path) as reopened:
        assert reopened.get_card_content(card.card_id) == "Changed"
    with pytest.raises(RuntimeError, match="closed"):
        workspace.__enter__()
    workspace.close()


def test_default_workspaces_are_unique_and_retained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOLDER_KIT_WORKSPACES", str(tmp_path))
    with holderkit.create("One") as first, holderkit.create("Two") as second:
        assert first.path.parent == second.path.parent == tmp_path
        assert first.path != second.path
    assert first.path.is_dir() and second.path.is_dir()


def test_clone_preserves_identity_and_reconstructs_analysis(
    remote: Remote, tmp_path: Path
) -> None:
    source_before = {
        p.relative_to(remote.source): p.read_bytes()
        for p in remote.source.rglob("*")
        if p.is_file()
    }
    path = tmp_path / "private"
    with holderkit.clone(remote.url, workspace=path) as workspace:
        assert workspace.remote_url == remote.url
        assert workspace.revision == remote.revision
        assert workspace.project_id == remote.project_id
        assert Path(workspace.root_path) == path / "data/projects/project"
        context = workspace
        assert context.get_card_content(remote.card_id) == "Original body #science"
        assert context.tags.list(remote.card_id) == ["science"]
        assert context.milestones.list(remote.card_id)[0]["description"] == "Review"
        assert len(context.connections.to_records()) == 1
        tables = context.to_dataframes(include_content=True)
        graph = context.to_networkx()
        context.update_card(remote.card_id, "Private edit")
    assert tables["cards"].shape[0] == 2
    assert graph.has_edge(remote.card_id, remote.other_id)
    assert source_before == {
        p.relative_to(remote.source): p.read_bytes()
        for p in remote.source.rglob("*")
        if p.is_file()
    }
    assert git(remote.bare, "rev-parse", "HEAD") == remote.revision
    with holderkit.reopen(path) as reopened:
        assert reopened.get_card_content(remote.card_id) == "Private edit"
    # Core can also recover the private projection after it is deliberately lost.
    (path / "data/server/holder.db").unlink()
    with holderkit.reopen(path) as recovered:
        assert recovered.get_card_content(remote.card_id) == "Private edit"


def test_clone_selected_tag_and_remote_branch(remote: Remote, tmp_path: Path) -> None:
    git(remote.bare, "tag", "analysis-start", remote.revision)
    git(remote.bare, "branch", "experiment", remote.revision)
    for ref in ("analysis-start", "experiment", remote.revision):
        with holderkit.clone(
            remote.url, workspace=tmp_path / ref, ref=ref
        ) as workspace:
            assert (
                json.loads((workspace.path / ".holder-kit.json").read_text())["ref"]
                == ref
            )
            assert workspace.revision == remote.revision


@pytest.mark.parametrize(
    "source",
    [
        "/tmp/live",
        "../live",
        "file:///tmp/live",
        "ext::command",
        "C:\\live",
        "https://user:secret@example.test/repo",
        "https://example.test/repo?token=secret",
    ],
)
def test_clone_rejects_local_sources_and_embedded_secrets(
    tmp_path: Path, source: str
) -> None:
    path = tmp_path / "destination"
    with pytest.raises(ValueError):
        holderkit.clone(source, workspace=path)
    assert not path.exists()


def test_existing_destinations_are_never_overwritten(
    remote: Remote, tmp_path: Path
) -> None:
    path = tmp_path / "existing"
    path.mkdir()
    sentinel = path / "keep.txt"
    sentinel.write_text("User data")
    with pytest.raises(FileExistsError):
        holderkit.create("New", workspace=path)
    with pytest.raises(FileExistsError):
        holderkit.clone(remote.url, workspace=path)
    assert sentinel.read_text() == "User data"


def test_invalid_ref_and_import_failure_remove_only_new_destination(
    remote: Remote, tmp_path: Path
) -> None:
    path = tmp_path / "failed"
    with pytest.raises(RuntimeError, match="Git operation failed"):
        holderkit.clone(remote.url, workspace=path, ref="missing-branch")
    assert not path.exists()
    git(remote.source, "rm", ".holder/project.json")
    git(
        remote.source,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.test",
        "commit",
        "-m",
        "Invalid manifest",
    )
    git(remote.source, "push", str(remote.bare), "HEAD")
    with pytest.raises(ValueError, match="manifest"):
        holderkit.clone(remote.url, workspace=path)
    assert not path.exists()


def test_reopen_rejects_unmarked_and_incomplete_workspaces(tmp_path: Path) -> None:
    with holderkit.open(tmp_path / "ordinary"):
        pass
    with pytest.raises(ValueError, match="completed"):
        holderkit.reopen(tmp_path / "ordinary")
    marker = tmp_path / "ordinary/.holder-kit.json"
    marker.write_text(json.dumps({"version": 1, "state": "initializing"}))
    with pytest.raises(ValueError, match="incomplete"):
        holderkit.reopen(tmp_path / "ordinary")


def test_reopen_rejects_symlinks_and_marker_path_escape(tmp_path: Path) -> None:
    with holderkit.create("Private", workspace=tmp_path / "private") as workspace:
        path = workspace.path
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (path / "escape").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation unavailable")
    with pytest.raises(ValueError, match="symlinks"):
        holderkit.reopen(path)
    (path / "escape").unlink()
    marker = path / ".holder-kit.json"
    data = json.loads(marker.read_text())
    data["project_path"] = "data/projects/../../../outside"
    marker.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="project path"):
        holderkit.reopen(path)
    assert list(outside.iterdir()) == []


def test_clone_rejects_symlink_before_checkout(remote: Remote, tmp_path: Path) -> None:
    # Create a Git symlink entry without needing host symlink privileges.
    blob = (
        subprocess.check_output(
            ["git", "-C", str(remote.source), "hash-object", "-w", "--stdin"],
            input=b"/outside",
        )
        .decode()
        .strip()
    )
    git(remote.source, "update-index", "--add", "--cacheinfo", f"120000,{blob},escape")
    git(
        remote.source,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.test",
        "commit",
        "-m",
        "Symlink fixture",
    )
    git(remote.source, "push", str(remote.bare), "HEAD")
    path = tmp_path / "private"
    with pytest.raises(ValueError, match="symlinks"):
        holderkit.clone(remote.url, workspace=path)
    assert not path.exists()


def test_reopen_rejects_git_alternates_and_encryption(tmp_path: Path) -> None:
    with holderkit.create("Private", workspace=tmp_path / "private") as workspace:
        root = Path(workspace.root_path)
    alternates = root / ".git/objects/info/alternates"
    alternates.parent.mkdir(exist_ok=True)
    alternates.write_text("/outside/objects\n")
    with pytest.raises(ValueError, match="Shared Git"):
        holderkit.reopen(workspace.path)
    alternates.unlink()
    bootstrap = root / ".holder/privacy.json"
    data = json.loads(bootstrap.read_text())
    data["mode"] = "encrypted_git"
    bootstrap.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="plain projects"):
        holderkit.reopen(workspace.path)


def test_clone_requires_import_capability_before_allocating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(holderkit._native, "PROJECT_IMPORT_SUPPORTED", 0)
    path = tmp_path / "private"
    with pytest.raises(NotImplementedError, match="import support"):
        holderkit.clone("https://example.test/project.git", workspace=path)
    assert not path.exists()


def test_checkout_does_not_run_configured_filters(
    remote: Remote, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (remote.source / ".gitattributes").write_text("cards/** filter=fixture\n")
    git(remote.source, "add", ".gitattributes")
    git(
        remote.source,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.test",
        "commit",
        "-m",
        "Attributes fixture",
    )
    git(remote.source, "push", str(remote.bare), "HEAD")
    marker = tmp_path / "filter-ran"
    probe = tmp_path / "filter.py"
    probe.write_text(
        f"import pathlib, sys\npathlib.Path({str(marker)!r}).touch()\nsys.stdout.buffer.write(sys.stdin.buffer.read())\n"
    )
    config_dir = tmp_path / "config/git"
    config_dir.mkdir(parents=True)
    subprocess.run(
        [
            "git",
            "config",
            "--file",
            str(config_dir / "config"),
            "filter.fixture.smudge",
            shlex.quote(sys.executable) + " " + shlex.quote(str(probe)),
        ],
        check=True,
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_dir.parent))
    with holderkit.clone(remote.url, workspace=tmp_path / "private") as workspace:
        assert workspace.get_card_content(remote.card_id) == "Original body #science"
    assert not marker.exists()
