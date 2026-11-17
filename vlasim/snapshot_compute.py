"""Snapshot optional official NeuSim compute sources without modifying their checkout."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    target = args.out / "source"
    target.mkdir()
    for name in ("LICENSE", "NOTICE"):
        shutil.copy2(args.source / name, target / name)
    for name in ("neusim_ramulator", "third_party/NeuSim"):
        shutil.copytree(args.source / name, target / name,
                        ignore=shutil.ignore_patterns(".git", "__pycache__", "*.so", "*.dylib", "build", ".DS_Store"))
    files = [{"path": str(p.relative_to(target)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
             for p in sorted(target.rglob("*")) if p.is_file()]
    (args.out / "source_manifest.json").write_text(json.dumps(dict(source=str(args.source.resolve()), files=files,
        scope="Source hashes authoritative; compute timing only, not calibrated hardware"), indent=2) + "\n")


if __name__ == "__main__":
    main()
