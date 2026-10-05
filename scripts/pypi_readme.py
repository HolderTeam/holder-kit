"""Resolve the README's inline Markdown links for the package description."""

import argparse
from pathlib import Path
import re
from urllib.parse import quote, urlsplit, urlunsplit


LINK = re.compile(r'(?P<image>!)?\[(?P<label>[^\]\n]+)\]\((?P<url>[^\s)]+)(?P<title>\s+"[^"\n]*")?\)')
FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
REPOSITORY = "HolderTeam/holder-kit"


def render_readme(content: str, root: Path, commit: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("README links require the full release commit SHA")
    root = root.resolve()

    def replace(match: re.Match[str]) -> str:
        target = match["url"]
        parts = urlsplit(target)
        if parts.scheme or parts.netloc or not parts.path:
            return match[0]
        path = (root / parts.path.lstrip("/")).resolve()
        relative = path.relative_to(root).as_posix()
        if not path.exists():
            raise ValueError(f"README link target does not exist: {target}")
        if match["image"]:
            base = f"https://raw.githubusercontent.com/{REPOSITORY}/{commit}/"
        else:
            kind = "tree" if path.is_dir() else "blob"
            base = f"https://github.com/{REPOSITORY}/{kind}/{commit}/"
        parsed = urlsplit(base + quote(relative))
        resolved = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parts.query, parts.fragment))
        return f'{match["image"] or ""}[{match["label"]}]({resolved}{match["title"] or ""})'

    result: list[str] = []
    fence = ""
    for line in content.splitlines(keepends=True):
        marker = FENCE.match(line)
        if marker:
            if not fence:
                fence = marker[1]
            elif marker[1][0] == fence[0] and len(marker[1]) >= len(fence):
                fence = ""
            result.append(line)
        else:
            result.append(line if fence else LINK.sub(replace, line))
    return "".join(result)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--readme", type=Path, default=Path("README.md"))
    args = parser.parse_args()
    original = args.readme.read_text(encoding="utf-8")
    args.readme.write_text(render_readme(original, args.readme.parent, args.commit), encoding="utf-8")


if __name__ == "__main__":
    main()
