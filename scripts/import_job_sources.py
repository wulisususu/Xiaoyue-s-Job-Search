from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CORE_ROOT = REPO_ROOT / "services" / "core-api"
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

from sqlalchemy.orm import Session  # noqa: E402

from app.config import AppSettings  # noqa: E402
from app.db import get_engine, init_db  # noqa: E402
from app.integrations.workfind import import_workfind  # noqa: E402
from app.integrations.xiaozhao import import_xiaozhao  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import WorkFind and Xiaozhao snapshots into Xiaoyue SQLite.")
    parser.add_argument("--workfind-db", type=Path, required=True)
    parser.add_argument("--workfind-relations", type=Path, required=True)
    parser.add_argument("--xiaozhao-jobs", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for path in (args.workfind_db, args.workfind_relations, args.xiaozhao_jobs):
        if not path.is_file():
            raise SystemExit(f"Source file not found: {path}")

    args.data_dir.mkdir(parents=True, exist_ok=True)
    settings = AppSettings(data_dir=args.data_dir)
    settings.vault_dir.mkdir(parents=True, exist_ok=True)
    init_db(settings)
    engine = get_engine(settings)
    try:
        with Session(engine) as session:
            workfind = import_workfind(session, args.workfind_db, args.workfind_relations)
            xiaozhao = import_xiaozhao(session, args.xiaozhao_jobs)
    finally:
        engine.dispose()

    print(json.dumps({"workfind": asdict(workfind), "xiaozhao": asdict(xiaozhao)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
