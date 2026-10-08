# Advanced: storage and reopening

Start with the [walkthrough](walkthrough.md) to create a project and analyse its
cards. `holderkit.create("Research")` and `holderkit.clone(remote_url)` choose
storage automatically. This guide covers choosing directories, selecting remote
revisions and returning to saved work.

Holder Kit provides one independent project per managed workspace. The workspace
contains its own Git checkout and SQLite projection; it does not attach to a
running Holder installation. Git must be installed for these entry points.

Clone requires a Core build with project import support. Older builds raise
`NotImplementedError` before creating files or contacting a remote. See
[Development](development.md#clone-build-requirements) for build requirements.

## Choose a storage directory

```python
import holderkit

with holderkit.create("Research", workspace="./research-lab") as lab:
    card = lab.context.create_card(
        lab.project.project_id, "Imported observation", "Measurements from Python",
    )
    print(lab.path, lab.project.root_path, lab.revision)
```

`workspace` is the new destination directory. It must not exist, even as an empty
directory. Omit it to allocate a unique workspace under `HOLDER_KIT_WORKSPACES`,
or the platform default: `$XDG_DATA_HOME/holder-kit/workspaces` (normally
`~/.local/share/holder-kit/workspaces`) on Linux/BSD,
`~/Library/Application Support/HolderKit/workspaces` on macOS, and
`%LOCALAPPDATA%/HolderKit/workspaces` on Windows. The base API needs neither pandas
nor NetworkX.

`Workspace.context` exposes the existing project/card/connection/tag/milestone
and analysis APIs. `Workspace.project` is the detached project snapshot from
opening the workspace. Each workspace supports exactly one project;
creating additional projects through the low-level context makes it ineligible
for managed reopening.

Each workspace stores a completion marker at `.holder-kit.json`, its private
database at `data/server/holder.db`, and one checkout under `data/projects/`.
The marker records the project's identity, checkout path and initial revision.
Use the managed APIs to open this directory; the database is reconstructed by
Core from durable project files when recovery is needed.

## Choose a remote revision and destination

```python
with holderkit.clone(
    "git@example.org:research.git",
    workspace="./research-copy",
    ref="main",
) as lab:
    records = lab.context.cards.to_records(include_content=True)
    # Optional extras use the same reconstructed records:
    tables = lab.context.to_dataframes()
    graph = lab.context.to_networkx()
    print(lab.source, lab.ref, lab.revision)
```

Sources must be explicit HTTPS, SSH (including SCP-style SSH), or `git://`
remotes. Local paths, `file://`, custom Git helper transports, submodules and
worktrees are unsupported. `git://` is unauthenticated; use SSH/HTTPS when
authentication is required. `ref` may be a branch, tag or commit available in the
clone; omitting it selects the remote's default HEAD. The checkout is detached at
the selected commit. Only committed data available at the remote is included,
not unpushed commits or uncommitted edits in another working tree.

Kit creates an independent clone, validates its storage layout, and asks core to
import its durable project data into a newly created empty database. Core preserves
project/card IDs, reconstructs indexes and derives storage roots from the private
checkout. Kit does not parse card Markdown or copy a source SQLite database.
This fresh import is separate from core's database-loss recovery/readiness checks.

Use existing Git credential helpers, SSH agent/key configuration and known hosts.
Do not embed credentials in URLs. Interactive terminal prompting is disabled.
Git stderr is suppressed on failure because it can disclose credentials; errors
identify the operation failure without reproducing the remote/helper diagnostics.
Checkout ignores global/system filters and templates and disables hooks. No
project-supplied hooks, submodules or scripts are run.

Only plain Holder projects with current durable manifests are supported.
Encrypted projects are rejected before keyring/decryption access. Resource and
location declarations can be reconstructed by core, but this API does not fetch
external asset bytes, provision private bindings, import secrets, or promise that
all attachments are available. Git LFS content is not fetched. Symlinks, shared
hard links, alternate Git object stores, and tracked daemon server state are
rejected. Historical revisions predating durable project manifests are unsupported.

## Reopen and close

```python
with holderkit.reopen("./research-copy") as lab:
    print(lab.context.cards.to_records())
```

Reopen accepts a completed Kit workspace marker, not an arbitrary Holder Home or
project directory. It validates paths and the single recorded project before
returning its context. It does not clone, fetch, pull, reset or discard edits.
The initialized `source`, requested `ref`, and selected `revision` remain recorded
in the marker; `revision` is not a live view of later local commits. Use ordinary
Git inspection of `lab.project.root_path` to review current history.

`close()` and context-manager exit release the native context and retain the
workspace, including edits made before an exception. Entity mutations retain
core's existing local-commit and failure semantics; isolation adds no transaction
or retry guarantees. Detached records/tables/graphs remain usable after close.
Concurrent use or modification of one workspace by multiple processes, direct
filesystem edits during operations, and concurrent replacement of workspace paths
are outside this API's consistency contract.

Failed initialization closes its native context and removes only the newly
allocated destination. Existing destinations are never cleaned or overwritten.
A marker is written only after successful initialization; interrupted, unmarked
workspaces cannot be reopened as complete. Remove an interrupted destination
deliberately after inspecting it, or choose a new destination for retry.

`holderkit.open(data_dir)` remains the low-level embedded API; managed entry
points do not fall back to it on an arbitrary Home.

For a runnable example with an explicit temporary directory and reopening, see
[`reopen_project.py`](../examples/reopen_project.py).
