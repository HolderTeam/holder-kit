# Publishing and finishing a project

Create or clone a project, do your analysis, then decide what to keep:

```python
import holderkit

project = holderkit.create("Research")
project.create_card("Result", "The experiment supports our hypothesis.")
published = project.push(
    remote_url="git@example.org:research.git",
    branch="experiments/results",
)
print(published.branch, published.revision)
project.close()
```

Replace the remote with a repository you can write to. For a cloned project,
omit `remote_url` to use its origin, or supply another destination. The branch
name is always required. Publication leaves the project open, so you can
continue working and push to the same branch again.

The first push creates a new branch. Kit refuses an existing branch that it
has not published to, and refuses the remote's advertised default branch.
Later pushes to the same destination and branch must be fast-forward. Kit
never pulls, merges, rebases or overwrites remote history. Your origin and
local checkout remain unchanged. Review and merge the published branch using
ordinary Git tools.

## Review before publishing

```python
preview = project.preview_push(
    remote_url="git@example.org:research.git",
    branch="experiments/results",
)
print(preview)
published = project.push(
    remote_url=preview.remote_url,
    branch=preview.branch,
    expected_revision=preview.revision,
)
```

Preview checks the remote and reports the destination, branch, current commit,
whether the branch is new, and whether the checkout has uncommitted changes.
`expected_revision` refuses to push if the project has changed since your review.

Only committed project history is published. Holder's editing methods make
local commits; Kit does not stage or commit extra files for you. Review your
history before publishing. Uncommitted edits, untracked files, notebooks and
external assets are not automatically included. The private database and Kit
marker live outside the project checkout and are not pushed.

Use your existing Git credentials and SSH setup. Credential-bearing URLs are
rejected, hooks are disabled and interactive terminal prompting is disabled.
Push errors retain local work and suppress Git diagnostics that might expose
credentials. If a connection fails after the remote accepted the push, its
outcome may be unknown. Retry the same destination, branch and unchanged
revision: Kit can recognize the exact attempted commit at the remote and record
success. An unrelated existing branch is still refused.

Publication records are local evidence of successful pushes. They do not
guarantee that a remote branch will continue to exist. An empty remote may not
advertise a default branch; choose your proposal branch name deliberately.

## Keep work or discard it

`project.close()` and context-manager exit retain your work, including after
an exception. See [Advanced: storage and reopening](workspaces.md) to return to
it later. Neither closing nor pushing deletes anything.

To deliberately remove the local project:

```python
print(project.preview_discard())
project.discard(confirm=True)
```

Discard is permanent. The preview identifies the exact directory and warns
about unpublished commits, uncommitted or untracked project files, and other
local artifacts. A successful push does not back up everything in that directory.
`confirm=True` explicitly acknowledges that loss without an interactive prompt.
You can preview or discard after closing.

Kit validates its storage marker, project identity and paths before closing
resources and removing the selected directory. Remote branches and external
assets remain intact. Affected handles become unusable. Repeated discard of a
missing directory raises `FileNotFoundError`; a replacement belonging to a
different project is refused. If removal fails partway, the error identifies
the remaining directory for inspection; recovery of all files is not guaranteed.

Push and discard apply to projects obtained from `create()`, `clone()` or
`reopen()`. Projects borrowed from a shared `Context` cannot use these operations.
Concurrent access or filesystem replacement during an operation is unsupported.

Run `./make.sh examples finish_project` for a temporary-data example. It does
useful work, closes the project, reviews disposal and removes it deliberately.
To also publish that example, run
`.venv/bin/python examples/finish_project.py --remote-url <url> --branch <new-branch>`.
