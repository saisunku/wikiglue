"""metrics/: the dashboard template and grafana-provisioning."""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METRICS = ROOT / "metrics"


def provision(tmp_path, *wikis):
    return subprocess.run([sys.executable, str(METRICS / "grafana-provisioning"), str(tmp_path), *wikis],
                          capture_output=True, text=True)


def exprs(d):
    return [t["expr"] for p in d["panels"] for t in p.get("targets", []) if "expr" in t]


def test_dashboard_for_the_wikis(tmp_path):
    assert provision(tmp_path, "home", "work").returncode == 0
    assert (tmp_path / "datasources" / "datasources.yaml").is_file()
    assert (tmp_path / "dashboards" / "dashboards.yaml").is_file()
    d = json.loads((tmp_path / "dashboards" / "wiki.json").read_text())
    var = d["templating"]["list"][0]
    assert var["query"] == "home,work"
    assert [o["value"] for o in var["options"]] == ["$__all", "home", "work"]
    text = "\n".join(exprs(d))
    # Lines naming no wiki are the first wiki's.
    assert '{{ or .w "home" }}' in text and '{{ or .wiki "home" }}' in text
    assert '"default"' not in text
    # Lint and digest: a 0 for each wiki.
    for title in ("Lint in the last 26 h", "Digest in the last 8 days"):
        e = next(t["expr"] for p in d["panels"] if p["title"] == title for t in p["targets"])
        assert re.findall(r'label_replace\(vector\(0\), "wiki", "([^"]+)"', e) == ["home", "work"]


def test_template_is_generic():
    text = (METRICS / "grafana" / "wiki.json").read_text()
    assert json.loads(text)["templating"]["list"][0]["query"] == "default"
    for word in ("deploy/", "sunku", "Sai"):
        assert word not in text


def test_bad_names(tmp_path):
    assert provision(tmp_path, "Home").returncode != 0
    assert provision(tmp_path, "home", "home").returncode != 0
    assert provision(tmp_path).returncode != 0


def test_compose_mounts_exist():
    compose = (METRICS / "compose.yml").read_text()
    for rel in re.findall(r"- \./([\w./-]+):", compose):
        assert (METRICS / rel).is_file(), rel
