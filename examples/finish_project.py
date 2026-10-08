"""Work on a temporary project, optionally publish it, then discard it."""

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

import holderkit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote-url", help="Optional Git destination you can write to")
    parser.add_argument("--branch", help="New publication branch at that destination")
    args = parser.parse_args()
    if bool(args.remote_url) != bool(args.branch):
        parser.error("Supply both --remote-url and --branch to publish")
    with TemporaryDirectory(prefix="holder-kit-finish-") as temporary:
        project = holderkit.create("Experiment", workspace=Path(temporary) / "project")
        project.create_card("Observation", "Useful experimental result")
        print(project.cards.to_records(include_content=True))
        if args.remote_url:
            preview = project.preview_push(remote_url=args.remote_url, branch=args.branch)
            print(preview)
            print(project.push(remote_url=preview.remote_url, branch=preview.branch,
                               expected_revision=preview.revision))
        project.close()
        print("Retained after close:", project.path.exists())
        print(project.preview_discard())
        project.discard(confirm=True)
        print("Removed locally:", not project.path.exists())


if __name__ == "__main__":
    main()
