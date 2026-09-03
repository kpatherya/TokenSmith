"""Observe the absence of learner-state storage and request fields for agent memory."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from _common import require_existing_path

from python_engine.tokensmith_store import connect, db_path

MEMORY_TERMS = ("learner", "mastery", "concept", "profile", "memory")
LEARNER_MEMORY_TERMS = ("learner", "mastery", "concept", "memory")


def engine_request_fields(repository_root: Path) -> list[str]:
    text = (repository_root / "src/shared/engine.ts").read_text(encoding="utf-8")
    match = re.search(r"export interface EngineChatRequest \{(.*?)^\}", text, flags=re.DOTALL | re.MULTILINE)
    if not match:
        raise RuntimeError("Could not locate EngineChatRequest in src/shared/engine.ts.")
    return re.findall(r"^\s{2}([A-Za-z_][A-Za-z0-9_]*)\??\s*:", match.group(1), flags=re.MULTILINE)


def main() -> None:
    parser = argparse.ArgumentParser(description="Dump TokenSmith's existing SQLite schema and EngineChatRequest fields to inspect the learner-memory gap.")
    parser.add_argument("user_data_path", help="Existing TokenSmith user-data directory containing tokensmith.sqlite.")
    args = parser.parse_args()

    user_data_path = str(require_existing_path(args.user_data_path, "user_data_path"))
    database = db_path(user_data_path)
    if not database.is_file():
        raise FileNotFoundError(f"No existing TokenSmith database at {database}; refusing to create one in a read-only harness.")

    # connect() is TokenSmith's production connection helper. query_only prevents this probe from changing data.
    with connect(user_data_path) as connection:
        connection.execute("PRAGMA query_only=ON")
        tables = [row["name"] for row in connection.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view') ORDER BY name")]
        broad_matches: list[str] = []
        learner_matches: list[str] = []
        print(f"Database: {database}\n")
        for table in tables:
            columns = [row["name"] for row in connection.execute(f'PRAGMA table_info("{table}")')]
            print(f"{table}: {', '.join(columns)}")
            for name in [table, *columns]:
                lowered = name.lower()
                if any(term in lowered for term in MEMORY_TERMS):
                    broad_matches.append(f"{table}.{name}" if name != table else table)
                if any(term in lowered for term in LEARNER_MEMORY_TERMS):
                    learner_matches.append(f"{table}.{name}" if name != table else table)

    root = Path(__file__).resolve().parents[1]
    fields = engine_request_fields(root)
    print("\nEngineChatRequest fields from src/shared/engine.ts:")
    print(", ".join(fields))
    print("\nBroad schema-name matches for learner/mastery/concept/profile/memory:")
    print("  " + ("\n  ".join(broad_matches) if broad_matches else "none"))
    print("\nLearner-memory-specific matches after excluding generic cleaning profiles:")
    print("  " + ("\n  ".join(learner_matches) if learner_matches else "none"))
    print("\nSuggested minimal learner-state schema only; this harness never creates it:")
    print("  learner_state(id, learner_id, concept_key, status, confidence, last_observed_at, source_chunk_id, session_id)")


if __name__ == "__main__":
    main()