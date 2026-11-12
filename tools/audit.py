"""Catalog rules from HANDOFF §5.

Exit 0 when every rule is PASS or WAIT. WAIT means the file it checks is not in the tree yet.
Exit 1 when any rule FAILs. Stdlib only.

    python tools/audit.py
"""
import ast
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BINARY_EXT = {
    ".exe", ".dll", ".pyd", ".so", ".dylib", ".node", ".wasm", ".bin",
    ".com", ".obj", ".o", ".a", ".lib", ".pyc", ".class",
}
SAMPLE_EXT = {".wav", ".mp3", ".flac", ".aif", ".aiff", ".ogg", ".opus", ".mid", ".midi"}
CODE_EXT = {".py", ".js", ".mjs"}
MAGICS = (b"MZ", b"\x7fELF", b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xfe\xed\xfa\xce", b"\xca\xfe\xba\xbe", b"\0asm")


def tracked():
    out = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    paths = []
    for raw in out.split(b"\0"):
        if raw:
            paths.append(ROOT / raw.decode("utf-8"))
    return paths


def rel(path):
    return path.relative_to(ROOT).as_posix()


def sniff(path):
    try:
        head = path.read_bytes()[:4]
    except OSError:
        return None
    for magic in MAGICS:
        if head.startswith(magic):
            return magic
    return None


def rule_binaries(files):
    bad = []
    for path in files:
        if path.suffix.lower() in BINARY_EXT or sniff(path):
            bad.append(rel(path))
    if bad:
        return "FAIL", "binaries: " + ", ".join(bad)
    return "PASS", "binaries: none tracked"


def rule_samples(files):
    voice_root = ROOT / "rookery" / "flock" / "voices"
    manifest = voice_root / "manifest.json"
    allowed = set()
    detail = "samples: none tracked"
    if voice_root.is_dir() and manifest.is_file():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            provenance = str(data.get("provenance", ""))
            if (data.get("schema") == "rookery.serum-voices/1"
                    and "Rookery authors" in provenance
                    and "original patches" in provenance):
                for entry in data.get("birds", {}).values():
                    for sample in entry.get("notes", []):
                        allowed.add((voice_root / sample["file"]).resolve())
                total = sum(path.stat().st_size for path in voice_root.rglob("*") if path.is_file())
                if allowed and total <= 8 * 1024 * 1024:
                    detail = (f"samples: {len(allowed)} first-party voice one-shots "
                              f"({total / 1024 / 1024:.2f} MiB, manifest provenance ok)")
                else:
                    allowed = set()
        except (OSError, ValueError, KeyError, TypeError):
            allowed = set()
    bad = [rel(path) for path in files
           if path.suffix.lower() in SAMPLE_EXT and path.resolve() not in allowed]
    if bad:
        return "FAIL", "samples: " + ", ".join(bad)
    return "PASS", detail


def dep_capped(dep):
    spec = dep.split(";", 1)[0]
    return any(op in spec for op in ("<", "==", "~="))


def rule_deps():
    path = ROOT / "pyproject.toml"
    if not path.exists():
        return "WAIT", "deps: pyproject.toml is not in the tree yet"
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    project = data.get("project", {})
    deps = list(project.get("dependencies") or [])
    for group in (project.get("optional-dependencies") or {}).values():
        deps.extend(group)
    bare = [dep for dep in deps if not dep_capped(dep)]
    if bare:
        return "FAIL", "deps: no upper bound on " + ", ".join(bare)
    if not deps:
        return "FAIL", "deps: pyproject.toml lists no dependencies"
    return "PASS", f"deps: {len(deps)} capped"


def yaml_list(text, key):
    lines = text.splitlines()
    for index, line in enumerate(lines):
        inline = re.match(rf"^{key}:\s*\[(.*)\]\s*$", line)
        if inline:
            return [item.strip().strip("'\"") for item in inline.group(1).split(",") if item.strip()]
        if re.match(rf"^{key}:\s*$", line):
            found = []
            for nxt in lines[index + 1 :]:
                if nxt.strip() == "" or nxt.strip().startswith("#"):
                    continue
                if re.match(r"^\S", nxt):
                    break
                item = re.match(r"^\s+-\s+[\"']?([^\"'#]+)", nxt)
                if not item:
                    break
                found.append(item.group(1).strip())
            return found
    return None


def yaml_scalar(text, key):
    match = re.search(rf"^{key}:\s*[\"']?([^\"'\n#]+)", text, re.M)
    if not match:
        return None
    return match.group(1).strip()


def registered_names(path):
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return set()
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "register_tool":
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                names.add(node.args[0].value)
            for kw in node.keywords:
                if kw.arg == "name" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    names.add(kw.value.value)
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if not any("TOOL" in name.upper() for name in targets):
                continue
            seq = node.value
            if isinstance(seq, (ast.List, ast.Tuple)):
                for elt in seq.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        names.add(elt.value)
                    elif isinstance(elt, (ast.List, ast.Tuple)) and elt.elts:
                        first = elt.elts[0]
                        if isinstance(first, ast.Constant) and isinstance(first.value, str):
                            names.add(first.value)
    return names


def rule_tools(files):
    path = ROOT / "plugin.yaml"
    if not path.exists():
        return "WAIT", "provides_tools: plugin.yaml is not in the tree yet"
    declared = yaml_list(path.read_text(encoding="utf-8"), "provides_tools")
    if not declared:
        return "FAIL", "provides_tools: missing from plugin.yaml"
    found = set()
    for code in files:
        if code.suffix == ".py" and "tests/" not in rel(code):
            found |= registered_names(code)
    if not found:
        return "FAIL", "provides_tools: plugin.yaml lists tools but register_tool names were not found"
    missing = [name for name in declared if name not in found]
    extra = sorted(found - set(declared))
    if missing or extra:
        return "FAIL", f"provides_tools: missing={missing or '-'} extra={extra or '-'}"
    return "PASS", f"provides_tools: {len(declared)} match register()"


def rule_requires():
    path = ROOT / "plugin.yaml"
    if not path.exists():
        return "WAIT", "requires_hermes: plugin.yaml is not in the tree yet"
    value = yaml_scalar(path.read_text(encoding="utf-8"), "requires_hermes")
    if not value:
        return "FAIL", "requires_hermes: missing from plugin.yaml"
    return "PASS", f"requires_hermes: {value}"


def code_lines(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    kept = []
    for line in text.splitlines():
        if path.suffix == ".py":
            line = line.split("#", 1)[0]
        elif line.strip().startswith("//"):
            continue
        kept.append(line)
    return kept


def rule_secrets(files):
    needles = (".env", "auth.json", "load_dotenv", "google_token.json", "client_secret")
    hits = []
    for path in files:
        if path.suffix.lower() not in CODE_EXT or path.name == "audit.py":
            continue
        for number, line in enumerate(code_lines(path), 1):
            scrubbed = re.sub(r"\b[\w.]+\.env\b", "", line)
            if re.search(r"(?<![\w.])\.env\b", scrubbed) or any(
                needle in scrubbed for needle in needles if needle != ".env"
            ):
                hits.append(f"{rel(path)}:{number}")
    if hits:
        return "FAIL", "secrets: " + ", ".join(hits)
    return "PASS", "secrets: no credential reads in code"


def rule_self_update(files):
    needles = ("git pull", "hermes update", "pip install -U", "pip install --upgrade")
    hits = []
    for path in files:
        if path.suffix.lower() not in CODE_EXT or path.name == "audit.py":
            continue
        for number, line in enumerate(code_lines(path), 1):
            low = line.lower()
            if any(needle in low for needle in needles):
                hits.append(f"{rel(path)}:{number}")
    if hits:
        return "FAIL", "self_update: " + ", ".join(hits)
    return "PASS", "self_update: none found"


def main():
    files = tracked()
    rows = [
        rule_binaries(files),
        rule_samples(files),
        rule_deps(),
        rule_tools(files),
        rule_requires(),
        rule_secrets(files),
        rule_self_update(files),
    ]
    failed = False
    for status, detail in rows:
        print(f"{status} {detail}")
        failed = failed or status == "FAIL"
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
