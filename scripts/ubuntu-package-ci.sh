#!/usr/bin/env bash
# Run inside a fresh matching Ubuntu container; export packages through /out.
set -euo pipefail
mode="${1:?build or install required}"
series="${2:?Ubuntu series required}"
source /etc/os-release
test "$VERSION_CODENAME" = "$series"
export DEBIAN_FRONTEND=noninteractive
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl gnupg
bash "$root/scripts/configure-holder-ppa.sh" "$series"
case "$mode" in
  build)
    apt-get install -y --no-install-recommends build-essential debhelper cmake ninja-build git \
      dh-python python3-dev python3-pytest python3-pandas python3-networkx libholder-dev
    mkdir -p /work/holder-kit /out
    tar -C "$root" --exclude=./.git --exclude=./build --exclude=./out --exclude=./debian \
      --exclude=__pycache__ --exclude=.pytest_cache --exclude=.venv -cf - . \
      | tar -C /work/holder-kit -xf -
    cd /work/holder-kit
    cp -a packaging/linux/debian debian
    dpkg-buildpackage -b -us -uc -j2
    cp /work/python3-holder-kit_*.deb /work/python3-holder-kit-dbgsym_*.ddeb \
      /work/holder-kit_*.buildinfo /work/holder-kit_*.changes /out/
    ;;
  install)
    apt-get install -y --no-install-recommends /out/python3-holder-kit_*.deb
    # These checks run before installing optional adapters or test dependencies.
    ! dpkg-query -W -f='${Status}' libholder-dev 2>/dev/null | grep -q 'install ok installed'
    ! command -v cc
    cd /tmp
    python3 -I "$root/scripts/test-installed-debian.py"
    apt-get install -y --no-install-recommends python3-pytest python3-pandas python3-networkx
    python3 -I -m pytest -q --import-mode=importlib -o cache_dir=/tmp/pytest-cache \
      "$root/tests/test_holder.py" "$root/tests/test_connections.py" \
      "$root/tests/test_pandas.py" "$root/tests/test_graph.py"
    ;;
  *) echo 'Expected build or install' >&2; exit 2 ;;
esac
