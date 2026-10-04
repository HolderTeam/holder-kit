# Holder Kit

Holder Kit provides CPython bindings for running libholder directly inside
a Python process. It offers a small typed interface for projects, cards and
explicit connections, tags and milestones, including detached dataclasses, plain dictionary records,
and optional pandas and NetworkX exports.

The compiled extension is `holderkit._native`. The `holderkit` package supplies the
small public wrapper and loads the database schema shipped from the selected
core source revision or SDK. It does not communicate with `holderd` and does not
implement a REST or command-line wrapper.

## Distribution and import migration

The Python distribution is now `holder-kit` and the import package is `holderkit`.
Replace `holder` in dependency declarations with `holder-kit`, including extras
such as `holder-kit[pandas]` and `holder-kit[graph]`. Replace `import holder` and
`from holder ...` with `import holderkit` and `from holderkit ...`. The former
`holder` package is not shipped, and there is no compatibility import shim.
In an existing environment, uninstall the former `holder` distribution before
installing the renamed wheel or checkout. The public methods, record contracts
and optional dependencies are unchanged.

The intended repository name is `holder-kit`. Until the separate GitHub rename,
source URLs, clone commands and CI checkout references continue to use
`HolderTeam/holder-python`. The local checkout directory need not be renamed.
The existing `HOLDER_PYTHON*` developer environment variables and CMake options
remain available; they configure the Python build. Upstream libholder names,
SDK paths and durable project formats retain their existing names.

## Build from source

The Bash developer entry point follows the other Holder repositories. It calls
the standard-library Python helper in `scripts/develop.py`, so you can normally
check out this repository and run `./make.sh` on Linux, macOS or BSD:

```sh
./make.sh --help                 # also accepts help and -h
./make.sh setup                  # create/reuse .venv, build editable test extras
./make.sh                       # build and run pytest
./make.sh check                  # build, pytest and strict mypy
./make.sh examples graph         # print connection-table and graph analysis
./make.sh examples tags          # semantic tag operations and table joins
./make.sh examples milestones    # milestone edits, calendar range and table joins
./make.sh wheel Release          # wheel in out/make/wheels
```

The default is a **local core source build**, using the first applicable location:

1. An explicit `HOLDER_PYTHON_CORE_SOURCE` path.
2. A sibling `../holder-core` checkout.
3. A managed `build/deps/holder-core` checkout.

If core is missing, the script stops before creating a virtualenv or installing
Python packages and prints two ways to provide it:

```sh
git clone https://github.com/HolderTeam/holder-core.git ../holder-core
# Or let the script prepare the recorded tested revision:
./make.sh setup-core

./make.sh
```

`setup-core` fetches the full commit recorded in `core-source.json` from the
official core repository into a temporary directory, verifies it, and moves the
completed checkout into `build/deps/holder-core`. It requires Git and network
access. It is idempotent for a clean matching checkout and refuses to overwrite
or update an existing divergent checkout. No submodule is involved.

Sibling and explicit source checkouts belong to the developer: builds never
switch branches, pull, reset or otherwise change their files. The selected
revision and working-tree status are printed; a different or modified developer
checkout may be used without claiming it matches the recorded tested revision.
Automatically discovered managed checkouts must match the recorded commit.
The chosen source revision is also recorded in `out/make/core-source.json`.

Before installing Python packages, the source workflow checks basic tools and
Python headers, then configures core with `BUILD_TESTING=OFF` to check native
prerequisites. Core's CMake configuration and README remain authoritative for
the native dependency set. Failures point to the exact core README and the
missing tool/dependency reported above. macOS builds discover an installed
Homebrew prefix and its OpenSSL prefixes; BSD users should install development
packages using their platform's ports/package manager. The script does not
install system packages or invoke sudo.

The script uses its own repository directory even when called from elsewhere,
and invokes `.venv` directly; shell activation is optional. `build` and `setup`
both install the editable package and test extras, including pandas and NetworkX.
Use `./make.sh test -k connections` to pass pytest arguments, and
`./make.sh typecheck` to check the installed development package without rebuilding.
`./make.sh clean` removes only script-owned `build/make` and `out/make` output;
it retains `.venv`, the managed core checkout, the SDK cache and other build directories.

Published SDK builds are an explicit alternative, using the shared SDK tool
described below and reusing its saved selection:

```sh
./make.sh --sdk check
./make.sh --sdk wheel Release
./make.sh sdk <tag-or-full-SHA>
```

`sdk` selects/fetches an SDK; use `--sdk` on subsequent builds to select that
workflow. Setting `HOLDER_CORE_REF` or `HOLDER_CORE_SDK` also explicitly selects
SDK builds unless an explicit source path is provided. `--sdk` combined with an
explicit source path is rejected. SDK dependency ABI limitations still apply;
there is no silent fallback from failed SDK builds to source builds.

`HOLDER_PYTHON` selects the interpreter used to create a new venv;
`HOLDER_PYTHON_VENV` selects its path. Build types have separate native build
directories, as do SDK and source builds. See help for the remaining commands
and environment options. Platform/compiler dependencies still need to be
installed as described below.

CI uses the latest green core SDK unless pinned. It resolves it once per run
and uses the same exact core commit on Linux, macOS, and Windows. An explicit
version tag or full commit SHA pins a Framework RC or release.

```console
git clone https://github.com/HolderTeam/holder-python.git
git clone https://github.com/HolderTeam/holder-core.git
cd holder-python
python3 -m venv .venv
source .venv/bin/activate
python scripts/core-sdk.py resolve
export HOLDER_CORE_SDK="$(python scripts/core-sdk.py fetch)"
export SKBUILD_CMAKE_BUILD_TYPE=RelWithDebInfo
python -m pip install -e .
```

The local `scripts/core-sdk.py` command delegates to the shared tool in the
sibling or managed core checkout. `HOLDER_CORE_SDK_TOOL` can select another checkout's
`scripts/core-sdk.py`. CI calls core's shared action directly, so SDK selection
and validation have one implementation owned and tested by core.

On Windows, run `fetch --github-env` in GitHub Actions, or set
`HOLDER_CORE_SDK` to the printed SDK path and configure CMake with the SDK's
bundled `vcpkg/scripts/buildsystems/vcpkg.cmake` toolchain,
`VCPKG_INSTALLED_DIR=<sdk>/vcpkg/installed`, `VCPKG_TARGET_TRIPLET=x64-windows`,
`VCPKG_MANIFEST_MODE=OFF`, and `VCPKG_APPLOCAL_DEPS=OFF`.
The SDK supplies prebuilt development dependencies;
no vcpkg bootstrap or dependency compilation runs in Holder Kit.

Use `python scripts/core-sdk.py resolve --core-ref <tag-or-full-SHA>` for an
explicit pin. Use `fetch --build-type Release` and `SKBUILD_CMAKE_BUILD_TYPE=Release`
for shipping builds. Development defaults to `RelWithDebInfo`. Archives are
cached by core commit, platform, architecture, and configuration; every fetch
checks the archive SHA256, size, and extracted manifest. Missing SDKs fail
without falling back to compiling core. Older Windows SDKs without bundled
development dependencies are rejected with a clear error.

The build uses CMake through scikit-build-core and requires a C/C++ compiler.
Linux and macOS also need core's distribution/Homebrew development dependencies.
The canonical Linux SDK uses the Ubuntu 24.04 dependency ABI. CI tests Python
3.12 and 3.14 on that baseline; native builds for other Ubuntu series will use
their matching core Debian packages. Mixing the static SDK with a newer
distribution's C++ dependency ABI can fail at import time.
Windows runtime DLLs and their license notices are installed beside the extension.
Installed SDK builds include `holderkit/_core_build.json` with the exact core commit,
version, platform, build configuration, and compiler, plus the matching schema.

For a manual source build without `make.sh`, clone `holder-core` beside this
repository and pass its absolute path to pip:

```sh
python -m pip install -e . \
  --config-settings=cmake.define.HOLDER_PYTHON_CORE_SOURCE="$(cd ../holder-core && pwd)"
```

This opt-in path builds core. Normal builds and CI use the published SDK.

CI runs on Python pushes and pull requests; manual CI accepts a `core_ref` pin.
The same workflow exposes `workflow_call` for core's publication integration:
`core_ref` selects the exact published core commit and `python_ref` selects the
Python source revision (default `main`). Both revisions are resolved once for
all jobs. There is no scheduled polling. Core's caller is a separate workflow,
so downstream test failures are reported independently of SDK publication.

## Test

```console
python -m pip install -e '.[test]'
python -m pytest
python -m mypy
```

Install the optional pandas adapter for notebook and scientific workflows:

```console
python -m pip install -e '.[pandas]'
```

Every test uses pytest's temporary directory and never opens a user's Holder
data directory or contacts a running daemon.

For native memory-safety work, configure a separate build with
`HOLDER_PYTHON_SANITIZE=address,undefined`. The option instruments the C
extension shim only. Core owns its own sanitizer coverage; the prebuilt core
library is not instrumented by this job.

## Example

```console
python examples/card_lifecycle.py
python examples/detached_records.py
python examples/pandas_analysis.py
python examples/graph_analysis.py  # requires both pandas and graph extras
python examples/tag_analysis.py    # requires pandas extra
python examples/milestone_analysis.py  # requires pandas extra
```

The examples create temporary data directories, exercise the current card
lifecycle, detached records and graph/table analysis, and remove their
directories when they exit.

## Current API

```python
from holderkit import Context

with Context("/path/to/isolated/data") as context:
    project = context.create_project("Notes")
    card = context.create_card(project.project_id, "A card", "Body")
    context.update_card(card.card_id, "New body", "New title")
    metadata = context.cards.to_records(project.project_id)
    records = context.cards.to_records(
        project.project_id, include_content=True
    )

# Detached records remain usable after the context has closed.
print(records[0]["content"])
```

With the pandas extra installed, the same detached contracts are available as
predictably typed DataFrames:

```python
import holderkit

with holderkit.open("./knowledge") as context:
    cards = context.cards.to_dataframe()
    complete = context.cards.to_dataframe(include_content=True)
    projects = context.projects.to_dataframe()
```

Export related tables together with the same schemas:

```python
import holderkit

with holderkit.open("./knowledge") as context:
    tables = context.to_dataframes(project_id=None, include_content=True)

# All tables are detached and remain usable after the context closes.
cards_with_projects = tables["cards"].merge(
    tables["projects"][["project_id", "name"]], on="project_id"
)
```

`to_dataframes()` returns a typed `DataFrames` dictionary containing `projects`,
`cards`, `connections`, `tags` and `milestones`. An optional project ID scopes the project row and
source cards; outgoing connections to other projects remain in the connection
table. Unknown IDs yield five empty tables with stable schemas. Card bodies
are omitted by default. Extraction reuses one project selection and the same
selected card records for connection, tag and milestone reads, but separate core calls do not form
an atomic snapshot. Errors propagate; no partial result is returned.

The default card table is metadata-only and has no `content` column. Complete
tables retain genuine empty bodies as empty strings. DataFrames are detached:
editing them never writes to Holder.

`Project` and `Card` are frozen, slotted dataclasses. `to_records()` returns
cheap metadata-only `CardMetadataRecord` dictionaries by default;
`include_content=True` returns `CompleteCardRecord` dictionaries using
libholder's paginated authoritative-file operation. All records contain only
standard-library values. Their stable schemas, null and timestamp conventions,
and extraction consistency are documented in
[Detached record contracts](docs/record-contracts.md).

A `Context` owns its native `holder_context` and can be closed explicitly or
with a context manager. Native runtime failures raise `holderkit.HolderError`;
invalid libholder arguments raise `ValueError`.

## Connections and graphs

Explicit connections use core's add/update and remove operations:

```python
import holderkit

with holderkit.open("./knowledge") as context:
    project = context.create_project("Graph demo")
    first = context.create_card(project.project_id, "Evidence")
    second = context.create_card(project.project_id, "Report")
    context.connections.add(second.card_id, first.card_id, "depends_on", "Needs evidence")
    links = context.connections.to_records(project.project_id)
    edges = context.connections.to_dataframe(project.project_id)  # pandas extra
    graph = context.to_networkx(project.project_id)                # graph extra
```

Install `holder-kit[graph]` (or `pip install -e '.[graph]'` from this checkout) for
NetworkX. Neither pandas nor NetworkX is imported by ordinary base-package use.
For the combined example, install `pip install -e '.[pandas,graph]'`.

`connections.add(from_card_id, to_card_id, kind, label=None)` adds or updates
one explicit card connection. Repeating the same source/target/kind updates its
label and core timestamp; different kinds remain distinct. Custom kinds are
allowed. `connections.remove(from_card_id, to_card_id, kind)` is a no-op when
the matching connection is absent. These are individual core operations, with
no Python batch transaction or optimistic concurrency promise.

Connection exports contain outgoing links of selected live source cards, once
each. They preserve core's `to_type`, nullable label and target title, and source
project ID. Backlinks are not duplicated, and hierarchy and inline wikilinks
are not converted to explicit connections. Core currently requires one link
read per source card. There is no atomic snapshot across those reads.

`context.to_networkx(project_id=None, include_content=False)` returns a detached
`MultiDiGraph` with card IDs as node identities and connection kinds as edge
keys. All selected live cards are nodes, including isolated cards. Node
attributes use card metadata records (or complete records with
`include_content=True`); edge attributes use the connection record contract.
Each selected card has `exported=True`. Card targets outside the selection or
unresolved in core are retained as minimal nodes with `card_id`, nullable
`title` and `exported=False`; this flag means their full record was not exported,
not that core confirmed their existence or deletion status. Project filtering
selects source cards, so cross-project target nodes can appear. Non-card targets
remain in connection records/tables but are excluded from this card graph.
Editing the graph or a connection table never writes back to Holder.

See [Detached record contracts](docs/record-contracts.md) for schemas and limits.

Tags use core's semantic operations; Python never parses or rewrites hashtag text:

```python
import holderkit

with holderkit.open("./knowledge") as context:
    project = context.create_project("Tags")
    card = context.create_card(project.project_id, "Evidence", "Prose #evidence")
    result = context.tags.add(card.card_id, "TODO")  # TagAddResult.ADDED
    result = context.tags.remove(card.card_id, "evidence")
    # TagRemoveResult.PRESENT_OUTSIDE_EDITABLE_TAG_LINE: prose is untouched.
    names = context.tags.list(card.card_id)
    editable = context.tags.list_editable(card.card_id)
    counts = context.tags.project_counts(project.project_id)
    matches = context.tags.cards_with_tag(project.project_id, "TODO")
    records = context.tags.to_records(project.project_id)
    tags = context.tags.to_dataframe(project.project_id)  # pandas extra
```

`TagRecord` describes a membership (`project_id`, `card_id`, normalized `tag`,
`editable`), not a separate tag entity with a fabricated ID. The boolean flag
means the tag is on core's editable trailing tag line; removing it can still
leave an occurrence in prose. Addition returns `ADDED` or `ALREADY_PRESENT`;
removal returns `REMOVED`, `NOT_PRESENT` or `PRESENT_OUTSIDE_EDITABLE_TAG_LINE`.
Compare enum members explicitly, not their truthiness. Search is
case-insensitive, project counts cover live cards, and exports are detached.
Join `tables["tags"]` to `tables["cards"]` on `project_id` and `card_id`.

Milestones use integer Unix seconds and core-generated IDs:

```python
import holderkit

with holderkit.open("./knowledge") as context:
    project = context.create_project("Calendar")
    card = context.create_card(project.project_id, "Review")
    milestones = context.milestones.add(
        card.card_id, 1791190800, end_at=1791194400, kind="Appointment",
    )  # returns the card's full updated milestone list
    milestone_id = milestones[0]["milestone_id"]
    updated = context.milestones.update(project.project_id, card.card_id, milestone_id, {
        "description": "Bring notes", "end_at": None,
    })  # omitted fields unchanged; None explicitly clears nullable fields
    calendar = context.milestones.in_range(project.project_id, 1791158400, 1791244800)
    records = context.milestones.to_records(project.project_id)
    frame = context.milestones.to_dataframe(project.project_id)  # pandas extra
    context.milestones.remove(card.card_id, milestone_id)
```

`list(card_id)`, `add()` and `update()` return detached `MilestoneRecord` data.
`in_range()` and exports return `ProjectMilestoneRecord` data, adding `project_id`
and `card_title` for joins. Calendar bounds are inclusive and select **start times**,
not overlapping intervals. Update ownership requires matching project/card/milestone
IDs; an absent or differently owned removal is a no-op. Join the combined
`tables["milestones"]` table to cards on `project_id` and `card_id`.

These operations preserve core's current limitations: add does not validate reversed
spans, and add/remove failures can leave index changes if the durable write fails.
They are not atomic transactions; see the record-contract documentation before
building retry or bulk-write workflows. Iteration and batching are the next slice.

The base package has no data-science dependencies. The broader
libholder API, concurrency support, stable-ABI wheels, public pip distribution, and Debian/Ubuntu `python3-holder-kit`
packaging remain later work. CI validates the SDK consumer on Linux, macOS,
and Windows.
