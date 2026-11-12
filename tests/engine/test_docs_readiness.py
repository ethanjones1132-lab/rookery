"""Docs are part of the submission: they must not drift from the registered tools."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _manifest_tools() -> list[str]:
    return [
        line.strip()[2:]
        for line in (ROOT / "plugin.yaml").read_text(encoding="utf-8").splitlines()
        if line.startswith("  - ")
    ]


def _catalog_tools() -> list[str]:
    lines = (ROOT / "plugin-catalog-draft" / "rookery.yaml").read_text(encoding="utf-8").splitlines()
    start = lines.index("  provides_tools:")
    tools = []
    for line in lines[start + 1:]:
        if not line.startswith("    - "):
            break
        tools.append(line.strip()[2:])
    return tools


def test_version_is_the_same_in_the_manifest_and_the_package():
    manifest = re.search(r'^version:\s*"([^"]+)"', (ROOT / "plugin.yaml").read_text(encoding="utf-8"), re.M)
    pyproject = re.search(r'^version\s*=\s*"([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M)
    package = re.search(r'^__version__\s*=\s*"([^"]+)"', (ROOT / "rookery" / "__init__.py").read_text(encoding="utf-8"), re.M)
    assert manifest and pyproject and package
    assert manifest.group(1) == pyproject.group(1) == package.group(1) == "0.2.0"
    assert 'requires_hermes: ">=0.23.0"' in (ROOT / "plugin.yaml").read_text(encoding="utf-8")


def test_readme_lists_exactly_the_registered_tools():
    registered = list(json.loads((ROOT / "rookery" / "tool_schemas.json").read_text(encoding="utf-8")))
    assert _manifest_tools() == registered
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    line = next(line for line in readme.splitlines() if line.startswith("- **Tools ("))
    named = re.findall(r"`([a-z_]+)`", line)
    assert named == registered
    assert "rookery_flock" not in named


def test_catalog_draft_matches_the_pinned_plugin():
    text = (ROOT / "plugin-catalog-draft" / "rookery.yaml").read_text(encoding="utf-8")
    registered = list(json.loads((ROOT / "rookery" / "tool_schemas.json").read_text(encoding="utf-8")))
    assert _catalog_tools() == registered
    assert "rookery_flock" not in _catalog_tools()
    assert "name: rookery" in text
    assert "repo: https://github.com/ethanjones1132-lab/rookery" in text
    assert 'sha: "<FULL_40_CHAR_SHA>"' in text
    assert 'version: "0.2.0"' in text
    assert 'requires_hermes: ">=0.23.0"' in text
    assert "requires_env: []" in text


def test_docs_do_not_ask_the_agent_to_drive_the_flock():
    for name in ("README.md", "docs/demo.md"):
        text = (ROOT / name).read_text(encoding="utf-8").lower()
        assert "give me a flock" not in text, name
    for name in ("README.md", "docs/demo.md", "docs/ship/LIVE-CHECKLIST.md"):
        text = (ROOT / name).read_text(encoding="utf-8").lower()
        assert "rookery_flock(action" not in text, name
