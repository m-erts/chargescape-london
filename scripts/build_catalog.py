"""Aggregate docs/data_catalog/*.md front matter into docs/data_catalog/README.md (a table)."""

from __future__ import annotations

from pathlib import Path

import yaml

CAT = Path(__file__).resolve().parents[1] / "docs" / "data_catalog"


def parse_front_matter(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    _, fm, _ = text.split("---", 2)
    try:
        return yaml.safe_load(fm) or None
    except yaml.YAMLError:
        return None


def main() -> None:
    rows = []
    for p in sorted(CAT.glob("*.md")):
        if p.name.startswith("_") or p.name == "README.md":
            continue
        fm = parse_front_matter(p)
        if fm:
            fm["_file"] = p.name
            rows.append(fm)

    def label(status: str) -> str:
        st = str(status).lower()
        parts = [w for w in ("observed", "proxy", "synthetic") if w in st]
        return " + ".join(parts) if parts else str(status)

    lines = [
        "# Data catalog",
        "",
        "One card per source. `status`: **observed** = real measurement, **proxy** = stands in for an unmeasured quantity, **synthetic** = model-generated.",
        "",
        "| id | title | provider | status | licence | spatial unit | temporal | size (MB) | script | card |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r.get('id', '')} | [{r.get('title', '')}]({r.get('url', '')}) | {r.get('provider', '')} | {label(r.get('status', ''))} | {r.get('licence', '')} | {r.get('spatial_unit', '')} | {r.get('temporal', '')} | {r.get('size_mb', '')} | `{r.get('script', '')}` | [{r['_file']}]({r['_file']}) |"
        )
    (CAT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {CAT / 'README.md'} with {len(rows)} datasets")


if __name__ == "__main__":
    main()
