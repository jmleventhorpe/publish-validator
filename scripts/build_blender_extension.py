"""Build the Blender extension zip.

    python scripts/build_blender_extension.py [--blender /path/to/blender]

1. Builds the publish_validator wheel with `uv build`.
2. Points blender_extension/blender_manifest.toml at it (and syncs the version).
3. Runs `blender --command extension build` to produce dist/publish_validator-<version>.zip.

Install the zip via Edit > Preferences > Get Extensions > Install from Disk.
"""

import argparse
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "blender_extension"
WHEELS = EXTENSION / "wheels"
DIST = ROOT / "dist"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--blender", default=shutil.which("blender") or "blender")
    args = parser.parse_args()

    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]

    shutil.rmtree(WHEELS, ignore_errors=True)
    subprocess.run(["uv", "build", "--wheel", "--out-dir", str(WHEELS)], cwd=ROOT, check=True)
    wheels = sorted(WHEELS.glob("publish_validator-*.whl"))
    if len(wheels) != 1:
        print(f"expected one wheel in {WHEELS}, found {wheels}", file=sys.stderr)
        return 1
    for extra in WHEELS.glob(".*"):  # uv leaves a .gitignore behind; Blender rejects it
        extra.unlink()

    manifest = EXTENSION / "blender_manifest.toml"
    text = manifest.read_text()
    text = re.sub(r'(?m)^version = ".*"$', f'version = "{version}"', text)
    text = re.sub(r"(?m)^wheels = \[.*\]$", f'wheels = ["./wheels/{wheels[0].name}"]', text)
    manifest.write_text(text)

    DIST.mkdir(exist_ok=True)
    subprocess.run(
        [
            args.blender,
            "--command",
            "extension",
            "build",
            "--source-dir",
            str(EXTENSION),
            "--output-dir",
            str(DIST),
        ],
        check=True,
    )
    print(f"Built {DIST / f'publish_validator-{version}.zip'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
