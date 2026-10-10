"""Shared helpers: locating and parsing the legacy query files."""

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEGACY_DIR = ROOT / "legacy_queries"
CACHE_DIR = ROOT / "llm_cache"
SNOWFLAKE_DIR = ROOT / "snowflake_sql"
DOCS_DIR = ROOT / "docs"
EXPECTED_DIR = ROOT / "expected"
REPORTS_DIR = ROOT / "reports"

CONVERTERS = ("llm", "baseline")


@dataclass
class LegacyQuery:
    qid: str          # e.g. "q03"
    name: str         # e.g. "q03_category_basket_stats"
    dialect: str      # "tsql" or "oracle"
    title: str
    ordered: bool
    sql: str          # full file text, header included
    body: str         # SQL without the metadata header

    @property
    def path(self) -> Path:
        return LEGACY_DIR / f"{self.name}.sql"


def _parse(path: Path) -> LegacyQuery:
    text = path.read_text()
    meta, body_lines = {}, []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("--") and ":" in stripped and not body_lines:
            key, _, value = stripped[2:].partition(":")
            meta[key.strip()] = value.strip()
        else:
            body_lines.append(line)
    return LegacyQuery(
        qid=path.stem.split("_")[0],
        name=path.stem,
        dialect=meta["dialect"],
        title=meta["title"],
        ordered=meta.get("ordered", "false").lower() == "true",
        sql=text,
        body="\n".join(body_lines).strip(),
    )


def load_queries() -> list[LegacyQuery]:
    return [_parse(p) for p in sorted(LEGACY_DIR.glob("q*.sql"))]


def converted_path(converter: str, q: LegacyQuery) -> Path:
    return SNOWFLAKE_DIR / converter / f"{q.name}.sql"
