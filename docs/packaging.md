# Packaging Holder Kit

The Python distribution is `holder-kit`; its import package is `holderkit`.
The version in `pyproject.toml` is independent of libholder and the Holder
Framework. The base package has no data-science dependencies; `pandas` and
`graph` are optional extras.

See [Building](building.md) for prerequisites and core selection, and
[Development](development.md) for checks to run before packaging.

## Wheels

The build backend is scikit-build-core, which invokes CMake to compile
`holderkit._native`. Wheels target the selected CPython and platform; they are
not stable-ABI wheels.

```sh
./make.sh wheel Release           # build with local core source
./make.sh --sdk wheel Release     # build with the selected core SDK
```

Both commands write wheels to `out/make/wheels`. For a manual SDK build, select
a Release SDK and a matching build configuration:

```sh
python scripts/core-sdk.py resolve --core-ref <tag-or-full-SHA>
export HOLDER_CORE_SDK="$(python scripts/core-sdk.py fetch --build-type Release)"
export SKBUILD_CMAKE_BUILD_TYPE=Release
python -m pip install build
python -m build --wheel --outdir dist
```

The package includes the matching `_schema.sql` and `py.typed`. SDK builds also
install the core manifest as `holderkit/_core_build.json`, recording the exact
core commit, version, platform, configuration and compiler. Source builds record
provenance in `out/make/core-source.json`; they do not currently install that
manifest into the Python package.

On Windows, SDK builds install runtime DLLs under `holderkit/.libs` and their
license notices under `holderkit/_licenses`. Unrepaired Linux and macOS SDK
wheels depend on the platform's native libraries. The canonical Linux SDK uses
the Ubuntu 24.04 dependency ABI. The release workflow bundles these dependencies
and checks the resulting wheel's platform compatibility as described below.

Validate a wheel in a fresh virtualenv outside the source checkout: import
`holderkit`, create temporary data, exercise the card lifecycle, and verify the
schema and typing resources. Test base use before installing optional adapters.
The Linux job in [`ci.yml`](../.github/workflows/ci.yml) provides the installed
SDK-wheel smoke test, including `_core_build.json` validation.

### Release wheels

[`release.yml`](../.github/workflows/release.yml) builds wheels for CPython
3.10–3.14 and a source archive. Supported wheel platforms are:

| Platform | Architecture | Minimum runtime |
| --- | --- | --- |
| Linux | x86_64 | glibc 2.39 (Ubuntu 24.04 or compatible) |
| Windows | x86_64 | Windows 10/11 |
| macOS | ARM64 | macOS 15 |

Release builds use the exact core commit and `Release` SDK configuration in
[`release-core.json`](../release-core.json). Ordinary development CI continues
to use latest-green. A Framework release should set this file to its core pin.

The wheels embed static core and include its native runtime dependencies, the
matching schema, type information and supplier notices. Installed wheels need
no core checkout, compiler or separately installed `libholder0`.

Linux repair bundles the dependency closure with private library names and uses
auditwheel to verify the `manylinux_2_39_x86_64` tag. GLib is included explicitly
because minimal Python environments may lack it. macOS uses delocate; Windows
uses delvewheel and removes the unmodified DLL copies before repair. Supplier
notices are carried in the distribution's licence metadata.

Each wheel is installed in a fresh virtualenv and tested before optional
adapters are installed, then runs the installed integration tests. Linux also
runs in clean Debian Python containers. The source archive is built and
installed with the same pinned SDK. The final distribution check requires all
15 wheels and the source archive, validates core identity and metadata, and
records file sizes and SHA256 hashes in the `release-manifest` artifact.

To inspect a candidate from the `release-distributions` artifact:

```sh
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install /path/to/holder_kit-*.whl
python -c "import holderkit; print(holderkit.__file__)"
```

Select the wheel matching the interpreter and platform. Older glibc, musl
Linux, other architectures and other Python implementations require an
explicit [native source build](building.md).

The manual workflow's `destination` defaults to `none`, which builds and tests
candidates. `pypi` or `testpypi` publishes only after all distribution checks
pass, using the corresponding GitHub environment and Trusted Publishing.
Publication requires the matching version tag, such as `v0.0.1` for the
version in `pyproject.toml`. Pull requests build candidates without publishing.

## Ubuntu packages

`python3-holder-kit` installs for the distribution's Python in
`/usr/lib/python3/dist-packages`. It builds against that Ubuntu series'
`libholder-dev` and uses the shared `libholder0` at runtime. pandas and NetworkX
are suggested packages, not required runtime dependencies.

The Debian packaging lives in [`packaging/linux/debian`](../packaging/linux/debian/).
It uses distro CMake and Python directly, without fetching pip build dependencies.

### System core build

With the Holder PPA enabled, install `libholder-dev`, Python development headers,
CMake, Ninja and compilers, then configure shared-library mode:

```sh
cmake -S . -B build/system -G Ninja -DHOLDER_USE_SYSTEM_CORE=ON
cmake --build build/system
```

System mode requires core's `Holder::Shared` target and rejects simultaneous SDK
or source selections. It installs the matching schema and `_core_build.json`,
recording the core version, Debian package revision and schema digest. It does
not copy libholder into the Python package.

For a Debian binary build in a disposable checkout with the build dependencies
from `packaging/linux/debian/control` installed:

```sh
cp -a packaging/linux/debian debian
dpkg-buildpackage -b -us -uc
```

### Package validation

[`ubuntu-packages.yml`](../.github/workflows/ubuntu-packages.yml) builds and tests
Noble (Ubuntu 24.04) and Resolute (Ubuntu 26.04) separately. It installs each
binary in a fresh container without development packages, tests ordinary Python
use, then installs optional adapters and runs integration tests.

To reproduce the Noble build and runtime checks with Docker:

```sh
mkdir -p out/packages
docker run --rm -v "$PWD:/source:ro" -v "$PWD/out/packages:/out" \
  ubuntu:24.04 bash /source/scripts/ubuntu-package-ci.sh build noble
docker run --rm -v "$PWD:/source:ro" -v "$PWD/out/packages:/out:ro" \
  ubuntu:24.04 bash /source/scripts/ubuntu-package-ci.sh install noble
```

For Resolute, use `ubuntu:26.04` and `resolute`. Keep each series' artifacts in
a separate output directory if testing both locally.

### Launchpad source packages

[`launchpad.yml`](../.github/workflows/launchpad.yml) is a manual workflow that
prepares source candidates for both Ubuntu series. Its inputs are:

| Input | Meaning |
| --- | --- |
| `version` | Must match `pyproject.toml` |
| `package_revision` | Positive Debian revision; increment for replacement uploads |
| `core_package_version` | Exact core package version before the Ubuntu suffix, such as `0.2.0-1` |
| `upload` | Defaults to false; when true, sign and upload to `ppa:holderteam/holder` |

Each candidate pins `libholder-dev` to the exact series-specific package version,
such as `0.2.0-1~noble1`. Runtime dependencies are generated against the compatible
shared ABI. Uploading requires the repository's `PPA_GPG_PRIVATE_KEY` secret.

To prepare a source candidate manually, use a clean disposable checkout and
Python 3.11 or newer (the preparation script uses `tomllib`):

```sh
python3 scripts/prepare-debian-source.py \
  --version 0.0.1 --package-revision 1 --series noble \
  --core-package-version '0.2.0-1~noble1'
debuild -S -d -us -uc
```

Use the actual Kit and core versions for the candidate. The script packages
committed files from `HEAD`, creates `debian/`, and writes the upstream archive
in the parent directory. The workflow saves the unsigned source candidate as an
artifact before optional signing and upload.
