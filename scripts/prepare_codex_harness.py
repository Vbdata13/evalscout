"""Copy the existing Valkyrie harness and pin only its Python setup."""
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import shutil

ROOT = Path(__file__).resolve().parents[1]
NAME = "codex-evalscout-py312"
ORIGINAL = "codex-v1.0.0"


def main():
    destination = ROOT / "private/valkyrie/harness" / NAME
    if destination.exists():
        raise SystemExit(f"Already exists: {destination}")
    with TemporaryDirectory(prefix="evalscout-harness-") as scratch:
        subprocess.run(["valkyrie", "agent", "download", ORIGINAL, "-o", scratch], check=True)
        source = Path(scratch) / ORIGINAL
        original = (source / "setup.sh").read_text()
        if original.count(" sync --frozen") != 1:
            raise SystemExit("Unexpected upstream install script. Inspect before patching.")
        shutil.copytree(source, destination)
    for name in ("contract.yaml", "setup.sh"):
        path = destination / name
        text = path.read_text().replace(ORIGINAL, NAME)
        if name == "setup.sh":
            text = text.replace(" sync --frozen", " sync --frozen --python 3.12")
        path.write_text(text)
    subprocess.run(["valkyrie", "agent", "push", str(destination), "--name", NAME], check=True)


if __name__ == "__main__":
    main()
