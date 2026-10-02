# holder-python

`holder-python` provides CPython bindings for running libholder directly inside
a Python process. It offers a small typed interface for projects and cards,
including detached dataclasses and plain dictionary record exports.

The compiled extension is `holder._native`. The `holder` package supplies the
small public wrapper and loads the database schema shipped from the selected
`holder-core` SDK. It does not communicate with `holderd` and does not
implement a REST or command-line wrapper.

## Build from source

Development builds use the latest green core SDK. CI resolves it once per run
and uses the same exact core commit on Linux, macOS, and Windows. An explicit
version tag or full commit SHA pins a Framework RC or release.

```console
git clone https://github.com/HolderTeam/holder-python.git
cd holder-python
python3 -m venv .venv
source .venv/bin/activate
python scripts/core-sdk.py resolve
export HOLDER_CORE_SDK="$(python scripts/core-sdk.py fetch)"
export SKBUILD_CMAKE_BUILD_TYPE=RelWithDebInfo
python -m pip install -e .
```

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

For explicit core source development, initialise the submodule and pass
`--config-settings=cmake.define.HOLDER_PYTHON_CORE_SOURCE=<absolute-core-source-path>`
to pip. This opt-in path builds core; normal CI does not initialise the submodule.

Scheduled CI runs every six hours to exercise new latest-green snapshots even
when holder-python has no source changes. Manual CI accepts a `core_ref` pin.

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
```

The examples create temporary data directories, exercise the current card
lifecycle and detached records, and remove their directories when they exit.

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

The base package has no data-science dependencies. NetworkX, the broader
libholder API, concurrency support, stable-ABI wheels, public pip distribution, and Debian/Ubuntu `python3-holder`
packaging remain later work. CI validates the SDK consumer on Linux, macOS,
and Windows.
