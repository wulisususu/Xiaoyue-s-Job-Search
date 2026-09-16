from __future__ import annotations

import argparse
import hashlib
import shutil
import zipfile
from pathlib import Path, PurePosixPath

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_ROOT = PROJECT_ROOT / "third_party" / "upstreams" / "_local"

UPSTREAMS = {
    "offer-harvester": "offer_harvester",
    "workfind": "workfind",
    "xiaozhao-radar": "xiaozhao_radar",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative_parts(name: str) -> tuple[str, ...]:
    posix = PurePosixPath(name.replace("\\", "/"))
    if posix.is_absolute() or ".." in posix.parts:
        raise ValueError(f"unsafe zip member: {name}")
    return tuple(part for part in posix.parts if part not in ("", "."))


def detect_single_root(zip_file: zipfile.ZipFile) -> str | None:
    roots: set[str] = set()
    for info in zip_file.infolist():
        parts = safe_relative_parts(info.filename)
        if parts:
            roots.add(parts[0])
    return next(iter(roots)) if len(roots) == 1 else None


def extract_snapshot(archive: Path, target: Path) -> str:
    if not archive.is_file():
        raise FileNotFoundError(archive)

    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive) as zip_file:
        root = detect_single_root(zip_file)
        for info in zip_file.infolist():
            parts = safe_relative_parts(info.filename)
            if root and parts and parts[0] == root:
                parts = parts[1:]
            if not parts or info.is_dir():
                continue
            destination = target.joinpath(*parts).resolve()
            if target.resolve() not in destination.parents:
                raise ValueError(f"zip member escapes target: {info.filename}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with zip_file.open(info) as source, destination.open("wb") as output:
                shutil.copyfileobj(source, output)

    return sha256(archive)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import local upstream ZIP snapshots into third_party/upstreams/_local."
    )
    parser.add_argument("--offer-harvester", type=Path)
    parser.add_argument("--workfind", type=Path)
    parser.add_argument("--xiaozhao-radar", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    LOCAL_ROOT.mkdir(parents=True, exist_ok=True)

    imported = 0
    for target_name, arg_name in UPSTREAMS.items():
        archive = getattr(args, arg_name)
        if archive is None:
            continue
        digest = extract_snapshot(archive.expanduser().resolve(), LOCAL_ROOT / target_name)
        imported += 1
        print(f"{target_name}: imported -> {LOCAL_ROOT / target_name}")
        print(f"{target_name}: sha256={digest}")

    if imported == 0:
        raise SystemExit("No archives supplied. See --help.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
