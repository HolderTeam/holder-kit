"""Run with an isolated interpreter after installing a release wheel."""

import argparse
import importlib.util
import json
from importlib.metadata import distribution
from pathlib import Path
import sys
import tempfile


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core-commit", required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    import holderkit
    from holderkit import _native

    package = Path(holderkit.__file__).parent
    installed = distribution("holder-kit")
    assert installed.version == args.version, installed.version
    assert _native.Context.__module__ == "holderkit._native"
    assert _native.PROJECT_IMPORT_SUPPORTED, "Release SDK must support cloning"
    assert importlib.util.find_spec("holder") is None
    assert importlib.util.find_spec("pandas") is None
    assert importlib.util.find_spec("networkx") is None
    assert (package / "py.typed").is_file()
    if sys.platform == "win32":
        notice = "third-party/microsoft-runtime.txt"
        assert notice in (installed.metadata.get_all("License-File") or [])
        files = installed.files or []
        notice_file = next(file for file in files if str(file).endswith(f"/licenses/{notice}"))
        license_text = installed.locate_file(notice_file).read_text(encoding="utf-8")
        assert "Source: https://visualstudio.microsoft.com/" in license_text
        assert "MICROSOFT" in license_text.upper() and "2022" in license_text
    info = json.loads((package / "_core_build.json").read_text())
    assert info["commit"] == args.core_commit, info
    assert info["build_type"] == "Release", info
    assert not any(name in sys.modules for name in ("pandas", "networkx"))
    with tempfile.TemporaryDirectory(prefix="kit-installed-wheel-") as temporary:
        with holderkit.open(Path(temporary) / "data") as context:
            project = context.create_project("Installed wheel")
            first = context.create_card(project.project_id, "First", "Before")
            second = context.create_card(project.project_id, "Second", "Second body")
            context.update_card(first.card_id, "After", "Renamed")
            context.connections.add(second.card_id, first.card_id, "depends_on")
            assert context.connections.to_records(project.project_id)
            records = context.cards.to_records(project.project_id, include_content=True)
            assert any(card["content"] == "After" for card in records)
            metadata_batches = list(project.cards(batch_size=1))
            complete_batches = list(project.cards(batch_size=1, include_content=True))
            assert [len(batch) for batch in metadata_batches] == [1, 1]
            assert [len(batch) for batch in complete_batches] == [1, 1]
            assert all("content" not in batch[0] for batch in metadata_batches)
            assert any(batch[0]["content"] == "After" for batch in complete_batches)
            if holderkit._native.CARD_COLLECTION_SUPPORTED:
                project.tags.add(first.card_id, "experiment")
                filtered = list(project.cards(tag="EXPERIMENT", roots=True, batch_size=1, include_content=True))
                assert len(filtered) == 1 and filtered[0][0]["card_id"] == first.card_id
                assert "After" in filtered[0][0]["content"]
                assert list(project.cards(tag="missing")) == []
            context.connections.remove(second.card_id, first.card_id, "depends_on")
            assert context.connections.to_records(project.project_id) == []
    print(f"Installed holder-kit {installed.version} passed with core {info['commit']}")


if __name__ == "__main__":
    main()
