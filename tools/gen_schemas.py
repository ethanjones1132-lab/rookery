"""Regenerate ``rookery/tool_schemas.json`` from ``rookery.tools.SCHEMAS``.

Order follows ``provides_tools`` in plugin.yaml, which is the order Hermes sees.
The plugin entry reads the JSON so ``register()`` never imports the engine.

    python tools/gen_schemas.py          # rewrite the file
    python tools/gen_schemas.py --check  # fail if the file is stale
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rookery import tools  # noqa: E402

TARGET = ROOT / "rookery" / "tool_schemas.json"
MANIFEST = ROOT / "plugin.yaml"


def manifest_tools() -> list[str]:
    """Return ``provides_tools`` from plugin.yaml in declared order."""
    names: list[str] = []
    inside = False
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if re.match(r"^provides_tools:\s*$", line):
            inside = True
            continue
        if inside:
            if line.strip() and not line.startswith((" ", "\t")):
                break
            item = re.match(r"^\s+-\s+[\"']?([^\"'\s#]+)", line)
            if item:
                names.append(item.group(1))
    return names


def schemas() -> dict[str, dict]:
    """Map every manifest tool to its schema, in manifest order."""
    names = manifest_tools()
    missing = [name for name in names if name not in tools.SCHEMAS]
    extra = [name for name in tools.SCHEMAS if name not in names]
    if missing or extra:
        raise SystemExit(f"tool drift: missing from SCHEMAS={missing} extra={extra}")
    return {name: tools.SCHEMAS[name] for name in names}


def render(data: dict[str, dict]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    data = schemas()
    text = render(data)
    if "--check" in argv:
        if TARGET.read_text(encoding="utf-8") != text:
            print(f"{TARGET.relative_to(ROOT)} is stale; run python tools/gen_schemas.py")
            return 1
        print(f"{TARGET.relative_to(ROOT)} matches tools.SCHEMAS and plugin.yaml")
        return 0
    TARGET.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {TARGET.relative_to(ROOT)} ({len(data)} tools)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
