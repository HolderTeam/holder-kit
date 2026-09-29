# holder-python

`holder-python` provides an initial CPython extension for running libholder
directly inside a Python process. It currently offers a deliberately small
vertical slice: open an isolated Holder context, create a project, and create,
list, retrieve, and update cards.

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
```

Every test uses pytest's temporary directory and never opens a user's Holder
data directory or contacts a running daemon.

For native memory-safety work, configure a separate build with
`HOLDER_PYTHON_SANITIZE=address,undefined`. The option instruments both the C
extension shim and the embedded `holder-core` target.

## Example

```console
python examples/card_lifecycle.py
```

The example creates a temporary data directory, exercises the complete current
card lifecycle, and removes the directory when it exits.

## Current API

```python
from holder import Context

with Context("/path/to/isolated/data") as context:
    project = context.create_project("Notes")
    card = context.create_card(project["project_id"], "A card", "Body")
    context.get_card_content(card["card_id"])
    context.update_card(card["card_id"], "New body", "New title")
    context.list_cards(project["project_id"])
```

Results are ordinary Python dictionaries, lists, and strings decoded from the
public libholder JSON API. A `Context` owns its native `holder_context` and can
be closed explicitly or with a context manager. Native runtime failures raise
`holder.HolderError`; invalid libholder arguments raise `ValueError`.

This first release intentionally omits the broader libholder API, high-level
domain objects, concurrency support, stable-ABI wheels, and packaging for
platforms other than Linux.
