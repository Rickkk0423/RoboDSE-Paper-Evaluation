"""Build an isolated snapshot of an existing NeuSim/Ramulator integration checkout."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


def snapshot(source, destination):
    if destination.exists():
        raise ValueError(f"snapshot already exists: {destination}; reuse its build or select a new --out")
    destination.mkdir(parents=True)
    for name in ("CMakeLists.txt", "LICENSE", "NOTICE"):
        shutil.copy2(source / name, destination / name)
    for name in ("native", "neusim_ramulator", "third_party/ramulator2"):
        shutil.copytree(source / name, destination / name,
                        ignore=shutil.ignore_patterns(".git", "__pycache__", "*.so", "*.dylib", "build", ".DS_Store"))
    records = []
    for path in sorted(destination.rglob("*")):
        if path.is_file():
            records.append({"path": str(path.relative_to(destination)),
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    revision = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"],
                              capture_output=True, text=True)
    return {"source": str(source), "source_repository_revision": revision.stdout.strip() if revision.returncode == 0 else None,
            "note": "Snapshot content hashes are authoritative; source checkout may contain changes.",
            "files": records}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", type=Path)
    ap.add_argument("--out", type=Path, default=Path(".native"))
    ap.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args()
    source, out = args.source.resolve(), args.out.resolve()
    if args.jobs < 1:
        ap.error("jobs must be positive")
    manifest = snapshot(source, out / "source")
    (out / "source_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    cmake = shutil.which("cmake") or str(Path(sys.executable).parent / "cmake")
    subprocess.run([cmake, "-S", str(out / "source"), "-B", str(out / "build"),
                    "-DCMAKE_BUILD_TYPE=Release",
                    f"-DFETCHCONTENT_SOURCE_DIR_YAML-CPP={out / 'source/third_party/ramulator2/ext/yaml-cpp'}",
                    f"-DFETCHCONTENT_SOURCE_DIR_FMT={out / 'source/third_party/ramulator2/ext/fmt'}"], check=True)
    subprocess.run([cmake, "--build", str(out / "build"), "--parallel", str(args.jobs)], check=True)
    print(f"Native backend ready at {out}")


if __name__ == "__main__":
    main()
