"""Exercise the distro package without a checkout, SDK or optional adapters."""

import importlib.util
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

import holderkit
from holderkit import _native


package = Path(holderkit.__file__).parent
assert package == Path("/usr/lib/python3/dist-packages/holderkit"), package
assert not list(package.rglob("libholder*")), "Core must come from libholder0"
assert importlib.util.find_spec("pandas") is None
assert importlib.util.find_spec("networkx") is None
info = json.loads((package / "_core_build.json").read_text())
assert info["source"] == "system-library"
assert info["soname"] == "libholder.so.0"
assert info["schema_sha256"] == hashlib.sha256((package / "_schema.sql").read_bytes()).hexdigest()
runtime_version = subprocess.check_output(
    ["dpkg-query", "-W", "-f=${Version}", "libholder0"], text=True,
).strip()
assert info["debian_version"] == runtime_version, (info, runtime_version)
libraries = subprocess.check_output(["ldd", _native.__file__], text=True)
assert "libholder.so.0 => /" in libraries, libraries
assert "not found" not in libraries, libraries
with tempfile.TemporaryDirectory() as directory:
    with holderkit.open(directory) as context:
        project = context.create_project("Installed package")
        first = context.create_card(project.project_id, "First", "Before")
        second = context.create_card(project.project_id, "Second")
        context.update_card(first.card_id, "After", "Renamed")
        context.connections.add(second.card_id, first.card_id, "depends_on")
        assert context.connections.to_records(project.project_id)
        records = context.cards.to_records(project.project_id, include_content=True)
        assert any(card["content"] == "After" for card in records)
        context.connections.remove(second.card_id, first.card_id, "depends_on")
        assert context.connections.to_records(project.project_id) == []
with tempfile.TemporaryDirectory() as directory:
    workspace = Path(directory) / "private"
    with holderkit.create("Installed workspace", workspace=workspace) as lab:
        card = lab.context.create_card(lab.project.project_id, "Retained", "Saved locally")
    with holderkit.reopen(workspace) as lab:
        assert lab.context.get_card_content(card.card_id) == "Saved locally"
print(f"Installed python3-holder-kit passed with libholder0 {runtime_version}")
