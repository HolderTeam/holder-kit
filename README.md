# holder-python

`holder-python` provides CPython bindings for running libholder directly inside
a Python process. It offers a small typed interface for projects, cards and
explicit connections, including detached dataclasses, plain dictionary records,
and optional pandas and NetworkX exports.

The compiled extension is `holder._native`. The `holder` package supplies the
small public wrapper and loads the database schema shipped from the selected
`holder-core` SDK. It does not communicate with `holderd` and does not
implement a REST or command-line wrapper.

## Build from source

The Bash developer entry point follows the other Holder repositories:

```sh
./make.sh --help                 # also accepts help and -h
./make.sh setup                  # create/reuse .venv, build editable test extras
./make.sh                       # build and run pytest
./make.sh check                  # build, pytest and strict mypy
./make.sh examples graph         # print connection-table and graph analysis
./make.sh wheel Release          # wheel in out/make/wheels
```

The script uses its own repository directory even when called from elsewhere,
and invokes `.venv` directly; shell activation is optional. `build` and `setup`
both install the editable package and test extras, including pandas and NetworkX.
Use `./make.sh test -k connections` to pass pytest arguments, and
`./make.sh typecheck` to check the installed development package without rebuilding.
`./make.sh clean` removes only script-owned `build/make` and `out/make` output;
it retains `.venv`, the SDK cache and other build directories.

Normal builds use the shared SDK tool described below, reusing the saved core
selection. `./make.sh sdk <tag-or-full-SHA>` selects a new pin; `./make.sh sdk`
selects latest-green. Set `HOLDER_CORE_REF` to select explicitly during a build,
or `HOLDER_CORE_SDK` to reuse an already prepared SDK. For local core development
(including distributions with a different dependency ABI), opt into a source build:

```sh
HOLDER_PYTHON_CORE_SOURCE=../holder-core ./make.sh check
HOLDER_PYTHON_CORE_SOURCE=../holder-core ./make.sh build Debug
```

`HOLDER_PYTHON` selects the interpreter used to create a new venv;
`HOLDER_PYTHON_VENV` selects its path. Build types have separate native build
directories, as do SDK and source builds. See help for the remaining commands
and environment options. Platform/compiler dependencies still need to be
installed as described below.

Development builds use the latest green core SDK. CI resolves it once per run
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
sibling core checkout. `HOLDER_CORE_SDK_TOOL` can select another checkout's
`scripts/core-sdk.py`. CI calls core's shared action directly, so SDK selection
and validation have one implementation owned and tested by core.

On Windows, run `fetch --github-env` in GitHub Actions, or set
`HOLDER_CORE_SDK` to the printed SDK path and configure CMake with the SDK's
bundled `vcpkg/scripts/buildsystems/vcpkg.cmake` toolchain,
`VCPKG_INSTALLED_DIR=<sdk>/vcpkg/installed`, `VCPKG_TARGET_TRIPLET=x64-windows`,
`VCPKG_MANIFEST_MODE=OFF`, and `VCPKG_APPLOCAL_DEPS=OFF`.
The SDK supplies prebuilt development dependencies;
no vcpkg bootstrap or dependency compilation runs in holder-python.

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
Installed SDK builds include `holder/_core_build.json` with the exact core commit,
version, platform, build configuration, and compiler, plus the matching schema.

For explicit core source development, clone `holder-core` beside this repository
and pass its absolute path to pip:

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
```

The examples create temporary data directories, exercise the current card
lifecycle, detached records and graph/table analysis, and remove their
directories when they exit.

## Current API

```python
from holder import Context

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
with holder.open("./knowledge") as context:
    cards = context.cards.to_dataframe()
    complete = context.cards.to_dataframe(include_content=True)
    projects = context.projects.to_dataframe()
```

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
with a context manager. Native runtime failures raise `holder.HolderError`;
invalid libholder arguments raise `ValueError`.

## Connections and graphs

Explicit connections use core's add/update and remove operations:

```python
with holder.open("./knowledge") as context:
    project = context.create_project("Graph demo")
    first = context.create_card(project.project_id, "Evidence")
    second = context.create_card(project.project_id, "Report")
    context.connections.add(second.card_id, first.card_id, "depends_on", "Needs evidence")
    links = context.connections.to_records(project.project_id)
    edges = context.connections.to_dataframe(project.project_id)  # pandas extra
    graph = context.to_networkx(project.project_id)                # graph extra
```

Install `holder[graph]` (or `pip install -e '.[graph]'` from this checkout) for
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
Combined `to_dataframes()`, milestones and tags remain subsequent slices.

The base package has no data-science dependencies. The broader
libholder API, concurrency support, stable-ABI wheels, public pip distribution, and Debian/Ubuntu `python3-holder`
packaging remain later work. CI validates the SDK consumer on Linux, macOS,
and Windows.
