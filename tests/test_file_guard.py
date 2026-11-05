"""runner/file-guard.ts: file tools stay inside the vault (run with node, if installed)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

GUARD = Path(__file__).resolve().parents[1] / "runner" / "file-guard.ts"

pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="needs node")


def outside(vault: Path, paths: list[str]) -> list[bool]:
    script = (f"import {{ outsideVault }} from {json.dumps(GUARD.as_uri())};"
              f"console.log(JSON.stringify({json.dumps(paths)}.map(p => outsideVault(p, {json.dumps(str(vault))}))))")
    out = subprocess.run(["node", "--input-type=module", "-e", script],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def test_paths_must_stay_in_the_vault(tmp_path):
    vault, other = tmp_path / "home", tmp_path / "work"
    (vault / "wiki").mkdir(parents=True)
    (other / "wiki").mkdir(parents=True)
    (vault / "wiki" / "sneaky").symlink_to(other / "wiki")
    inside = [".", "wiki", "wiki/new/page.md", "@wiki/x.md", str(vault / "wiki"), "wiki/../AGENTS.md"]
    escape = ["..", "../work/wiki", str(other), "/etc/passwd", "~/x", "wiki/sneaky/page.md",
              "wiki/sneaky", "/var/lib/wiki-jobs/transcripts"]
    assert outside(vault, inside) == [False] * len(inside)
    assert outside(vault, escape) == [True] * len(escape)
