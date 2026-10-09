# Developing Holder Kit

Start with [Building](building.md) to install an editable checkout and its test
dependencies. [Packaging](packaging.md) covers distributable artifacts.

## Code layout and ownership

Holder Kit embeds libholder in the Python process. It does not talk to a running
`holderd` or wrap the Framework REST API.

| Location | Responsibility |
| --- | --- |
| `src/native/module.c` | CPython extension, exposed as `holderkit._native` |
| `src/holderkit/` | Public Python API, typed records and optional adapters |
| `tests/` | API, adapter and developer-script tests |
| `examples/` | Runnable examples for project and analysis APIs |
| `scripts/develop.py` | Developer environment and build commands |
| `CMakeLists.txt` | Native extension build and resource installation |

Keep reusable storage and domain behavior in holder-core. The Python layer calls
core's semantic operations, including tag and milestone edits, rather than
reimplementing them by parsing or rewriting card files. Core also owns SDK
selection and validation; `scripts/core-sdk.py` delegates to its shared tool.

The package ships the schema from the selected core source or SDK as
`holderkit/_schema.sql`. Installed packages must work without a source checkout.

## Tests and type checking

```sh
./make.sh                         # rebuild and run pytest
./make.sh check                   # rebuild, pytest and strict mypy
./make.sh test Debug -k connections
./make.sh typecheck               # mypy without rebuilding
```

Use `--sdk` for SDK builds, for example `./make.sh --sdk check`.
`test` forwards trailing arguments to pytest; `typecheck` forwards them to mypy.
`setup` and `build` install the editable package and test extras without running
checks. The test extra includes pandas, NetworkX and their type stubs.

To check an already installed development environment directly:

```sh
.venv/bin/python -m pytest
.venv/bin/python -m mypy
```

Tests use pytest's temporary directories. They do not open a user's Holder data
directory or contact a running daemon. Follow that pattern for new tests.

## Examples

```sh
./make.sh examples                # run all examples
./make.sh examples lifecycle
./make.sh examples records
./make.sh examples pandas
./make.sh examples graph
./make.sh examples tags
./make.sh examples milestones
./make.sh examples make_project
./make.sh examples finish_project
```

`make_project` uses automatic storage and keeps the project it creates. The other
examples use temporary data directories and clean up on exit. Examples can also
be run directly with the development environment's Python. The pandas, tag and
milestone analysis examples require the pandas extra; graph analysis uses both
pandas and graph extras. Ordinary base-package use imports neither dependency.

The workspace tests start disposable Git servers on loopback to test real remote
clones. They require Git and permission to bind/connect local sockets. Fixtures
use temporary contexts and bare repositories, never a live Holder project.

## Public API contracts

`Context` owns the native `holder_context`; close it explicitly or use a context
manager. Native runtime failures raise `holderkit.HolderError`, and invalid core
arguments raise `ValueError`. `Project` is a live interface to one project;
its properties read current state. `Card` remains a frozen, slotted snapshot.
Use `Project.to_record()` for detached project values. Managed Projects own
their context; Projects obtained from a Context borrow it and close independently.

Records, DataFrames and graphs are detached data. They remain usable after the
context closes, and editing them does not write back to Holder. Card exports
omit bodies by default. Exporting related tables makes separate core reads and
does not promise an atomic snapshot.

The [Detached record contracts](record-contracts.md) document field schemas,
nulls, timestamps, project filtering, graph endpoints, tag results and milestone
mutation limits. Consult those contracts when changing the API, and keep them
and the examples consistent with the code. Test empty exports, optional
dependencies, ownership checks and failure behavior where relevant.

## Clone build requirements

Clone uses Core's `holder_project_import` API. The release SDK and development
source pins select `bd88c6d008a6d3cb5b427252aa010e96834bb058`, which provides it.
To select and build that published SDK:

```sh
./make.sh sdk bd88c6d008a6d3cb5b427252aa010e96834bb058
./make.sh --sdk setup
```

For Core development, use an explicit source override:

```sh
HOLDER_KIT_CORE_SOURCE=/path/to/holder-core ./make.sh setup
```

Selecting an older SDK without project import support still makes clone raise
`NotImplementedError` before creating storage or contacting the remote.

## Native sanitizers

For native memory-safety work, use a separate pip/CMake build with
`HOLDER_KIT_SANITIZE=address,undefined`. For example, with `HOLDER_CORE_SDK` set:

```sh
python -m pip install . 'pytest>=8' \
  --config-settings=build-dir=build/sanitize/{wheel_tag} \
  --config-settings=cmake.define.HOLDER_KIT_SANITIZE=address,undefined
```

Run this in a separate virtualenv. On Linux, preload the compiler's ASan runtime
before running Python; see the sanitizer steps in
[`ci.yml`](../.github/workflows/ci.yml) for the runtime settings and lifecycle
smoke tests. This instruments the C extension shim only. Core owns its own
sanitizer coverage; the prebuilt SDK library is not instrumented. The developer
script clears the sanitizer option for its ordinary builds, so use direct pip
or CMake commands for this configuration.

## Continuous integration

[`ci.yml`](../.github/workflows/ci.yml) runs on pushes to `main` and pull requests.
It resolves the latest green core SDK once and uses the same exact core commit
across Linux, macOS and Windows. Manual runs accept a `core_ref` tag or full SHA.

The Ubuntu 24.04 jobs cover Python 3.12 with the complete tests, strict mypy and
an installed-wheel smoke test, and Python 3.14 with shim sanitizers. macOS and
Windows run base API tests and the lifecycle example. Ubuntu package tests are
covered separately in [Packaging](packaging.md).

The workflow also exposes `workflow_call`: `core_ref` selects the published
core commit and `kit_ref` selects the Holder Kit revision, defaulting to `main`.
Both revisions are resolved once for all jobs. Core's publication integration
calls this separate workflow, so consumer test failures are reported independently
of SDK publication. There is no scheduled polling.

## Package names

The distribution is `holder-kit`, the import is `holderkit`, and the repository
is `HolderTeam/holder-kit`. When updating an older environment, uninstall the
former `holder` distribution and replace `import holder` with `import holderkit`.
Dependency declarations use `holder-kit`, `holder-kit[pandas]` or
`holder-kit[graph]`. There is no compatibility import shim.

## Filtered card batch build requirements

Filtered `project.cards(...)` batches use Core's `holder_card_collection_page_json`
API, advertised by `HOLDER_HAS_CARD_COLLECTION_PAGE`. The currently pinned SDK
predates this API. To develop and test it before a supporting SDK is published,
use the explicit source override above with the Core collection-page branch.
Existing unfiltered batches continue to work with the pinned SDK; requesting
filters or explicit ordering on it raises `NotImplementedError`. Move both SDK
and source pins together after the Core change has a published SDK, and run
Kit's filtered tests and installed-wheel checks against that exact revision.
