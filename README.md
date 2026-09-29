# holder-python

`holder-python` provides CPython bindings for running libholder directly inside
a Python process. It offers a small typed interface for projects and cards,
including detached dataclasses and plain dictionary record exports.

The compiled extension is `holder._native`. The `holder` package supplies the
small public wrapper and loads the database schema shipped from the pinned
`holder-core` submodule. It does not communicate with `holderd` and does not
implement a REST or command-line wrapper.

## Build from source

Linux and CPython 3.14 are the initial supported environment. Clone with the
submodule, create a virtual environment, and install in editable mode:

```console
git clone --recurse-submodules https://github.com/HolderTeam/holder-python.git
cd holder-python
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

For an existing checkout, initialise the dependency first:

```console
git submodule update --init --recursive
```

The build uses CMake through scikit-build-core and requires the C/C++ compiler
and development libraries required by `holder-core`.

## Test

```console
python -m pip install -e '.[test]'
python -m pytest
python -m mypy
```

Every test uses pytest's temporary directory and never opens a user's Holder
data directory or contacts a running daemon.

For native memory-safety work, configure a separate build with
`HOLDER_PYTHON_SANITIZE=address,undefined`. The option instruments both the C
extension shim and the embedded `holder-core` target.

## Example

```console
python examples/card_lifecycle.py
python examples/detached_records.py
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

The base package has no data-science dependencies. DataFrames, NetworkX, the
broader libholder API, concurrency support, stable-ABI wheels, and packaging
for platforms other than Linux remain out of scope for this increment.
