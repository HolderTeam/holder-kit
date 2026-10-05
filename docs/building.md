# Building Holder Kit

This guide covers building and installing a checkout. See
[Development](development.md) for tests and code changes, and
[Packaging](packaging.md) for wheels and Ubuntu packages.

## Prerequisites

Holder Kit requires Python 3.10 or newer with virtualenv support and development
headers, CMake 3.22 or newer, and C/C++ compilers. Linux, macOS and BSD builds
also need `pkg-config` and core's native development dependencies. Use the
selected holder-core checkout's README and CMake configuration for that
dependency list.

On macOS, install Xcode Command Line Tools and the required Homebrew packages.
The developer script discovers Homebrew and its OpenSSL prefixes; set
`CMAKE_PREFIX_PATH` if CMake cannot find a library. On BSD, use the platform's
ports or package manager. The script does not install system packages.

## Build with core source

`make.sh` is the Bash entry point on Linux, macOS and BSD. It runs
`scripts/develop.py`, creates or reuses `.venv`, and installs Holder Kit as an
editable package with all test dependencies, including pandas and NetworkX.

From the holder-kit checkout:

```sh
git clone https://github.com/HolderTeam/holder-core.git ../holder-core
./make.sh setup
```

If you already have a sibling holder-core checkout, just run `./make.sh setup`.
To fetch the tested revision recorded in `core-source.json` instead:

```sh
./make.sh setup-core
./make.sh setup
```

Core source selection uses the first applicable location:

1. `HOLDER_KIT_CORE_SOURCE`, an explicit checkout path.
2. The sibling `../holder-core` checkout.
3. The managed `build/deps/holder-core` checkout.

`setup-core` requires Git and network access. It verifies the recorded commit
before placing the checkout in `build/deps/holder-core`. It accepts an existing
clean checkout at that revision and refuses to update or overwrite a divergent
checkout. A sibling checkout takes precedence over the managed checkout.

Builds leave developer-owned core checkouts on their current branch and revision.
They print the selected revision and working-tree status, and record source
provenance in `out/make/core-source.json`. An automatically discovered managed
checkout must match the recorded commit.

Before creating a virtualenv or installing Python packages, the source workflow
checks tools, Python headers and core's CMake prerequisites with
`BUILD_TESTING=OFF`. If core is missing or configuration fails, fix the reported
prerequisite and rerun the command.

The script uses its own repository directory and invokes the virtualenv directly;
shell activation is optional. To use an existing checkout elsewhere:

```sh
HOLDER_KIT_CORE_SOURCE=/absolute/path/to/holder-core ./make.sh setup
```

For a manual build without the developer script, create a virtualenv and pass
the core source path explicitly:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e . \
  --config-settings=cmake.define.HOLDER_KIT_CORE_SOURCE=/absolute/path/to/holder-core
```

Direct pip/CMake builds require an explicit core selection; the source discovery
above belongs to the developer script.

## Build with a published core SDK

SDK builds consume a prebuilt core library. The local `scripts/core-sdk.py`
delegates SDK selection and validation to core's shared tool. Provide a sibling
or managed core checkout, or set `HOLDER_CORE_SDK_TOOL` to another checkout's
`scripts/core-sdk.py`.

```sh
./make.sh sdk <tag-or-full-SHA>
./make.sh --sdk setup
```

Omitting the reference selects `latest-green`. Subsequent `--sdk` builds reuse
the saved selection in `out/core-selection.json`. `HOLDER_CORE_REF` or
`HOLDER_CORE_SDK` also selects the SDK workflow unless `HOLDER_KIT_CORE_SOURCE`
is set. Combining `--sdk` with an explicit source path is rejected.

For manual builds on Linux or macOS:

```sh
python3 -m venv .venv
. .venv/bin/activate
python scripts/core-sdk.py resolve --core-ref <tag-or-full-SHA>
export HOLDER_CORE_SDK="$(python scripts/core-sdk.py fetch)"
export SKBUILD_CMAKE_BUILD_TYPE=RelWithDebInfo
python -m pip install -e .
```

SDK archives are cached by core commit, platform, architecture and configuration.
Fetching verifies the archive SHA256, size and extracted manifest. Missing or
incompatible SDKs fail without falling back to a source build.

Linux and macOS SDK builds still need core's native development dependencies.
The canonical Linux SDK uses the Ubuntu 24.04 dependency ABI. Mixing it with
another distribution's C++ dependency ABI can cause import failures; use a
matching source build or the series-specific [Ubuntu package](packaging.md#ubuntu-packages).

### Windows

Use an MSVC developer environment and a supported Python. Run the Python helper
directly if Bash is unavailable:

```powershell
python scripts/develop.py sdk <tag-or-full-SHA>
python scripts/develop.py --sdk setup
```

The helper configures the SDK's bundled vcpkg toolchain and prebuilt dependencies.
For direct pip/CMake builds, set `HOLDER_CORE_SDK` to the fetched SDK path and
pass these CMake definitions:

| Definition | Value |
| --- | --- |
| `CMAKE_TOOLCHAIN_FILE` | `<sdk>/vcpkg/scripts/buildsystems/vcpkg.cmake` |
| `VCPKG_INSTALLED_DIR` | `<sdk>/vcpkg/installed` |
| `VCPKG_TARGET_TRIPLET` | `x64-windows` |
| `VCPKG_MANIFEST_MODE` | `OFF` |
| `VCPKG_APPLOCAL_DEPS` | `OFF` |

`fetch --github-env` supplies the SDK environment in GitHub Actions. Holder Kit
does not bootstrap vcpkg or compile the SDK's dependencies. Windows SDKs without
bundled development dependencies are rejected.

## Build settings and output

Build commands accept `Debug`, `Release`, `RelWithDebInfo` or `MinSizeRel`:

```sh
./make.sh setup Debug
./make.sh --sdk setup Release
```

The default is `RelWithDebInfo`. SDK builds select a Release SDK for `Release`
and `MinSizeRel`, and a RelWithDebInfo SDK otherwise. Source and SDK builds, and
each build type, have separate native directories under `build/make`.

| Environment variable | Purpose |
| --- | --- |
| `HOLDER_KIT` | Bootstrap Python interpreter; otherwise reuse the selected venv or use `python3` |
| `HOLDER_KIT_VENV` | Virtualenv path; defaults to `.venv` |
| `HOLDER_KIT_CORE_SOURCE` | Explicit core source checkout |
| `HOLDER_CORE_SDK` | Prepared SDK directory containing `libholder-manifest.json` |
| `HOLDER_CORE_REF` | SDK tag, full commit SHA or `latest-green` |
| `HOLDER_CORE_SDK_TOOL` | Path to core's shared SDK script |
| `BUILD_TYPE` | Default native build type |
| `CMAKE_BUILD_PARALLEL_LEVEL` | Build parallelism limit |

`./make.sh clean` removes only `build/make` and `out/make`. It retains `.venv`,
the managed core checkout, SDK cache and other build directories. Run
`./make.sh --help` for the complete command reference.
