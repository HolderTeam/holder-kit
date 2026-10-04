#!/usr/bin/env bash
# Configure the public, signed Holder PPA in an Ubuntu test container.
set -euo pipefail
series="${1:?Ubuntu series required}"
case "$series" in noble|resolute) ;; *) exit 2 ;; esac
fingerprint=10560FF013CCB9D672B345B6128AA24BF15EC3B0
curl -fsSL "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x${fingerprint}" \
  -o /tmp/holder-ppa.asc
actual="$(gpg --show-keys --with-colons /tmp/holder-ppa.asc | awk -F: '$1 == "fpr" {print $10; exit}')"
test "$actual" = "$fingerprint"
gpg --batch --yes --dearmor -o /usr/share/keyrings/holder-ppa.gpg /tmp/holder-ppa.asc
printf 'deb [signed-by=/usr/share/keyrings/holder-ppa.gpg] https://ppa.launchpadcontent.net/holderteam/holder/ubuntu %s main\n' \
  "$series" > /etc/apt/sources.list.d/holder.list
apt-get update
