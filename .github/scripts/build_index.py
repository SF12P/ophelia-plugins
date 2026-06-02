"""
.github/scripts/build_index.py
Reads all .py files in plugins/ and regenerates index.json automatically.
Each plugin file must have NAME, DESCRIPTION, VERSION, and TRIGGERS defined.
Optional: COMMANDS, TAGS, REQUIRES

Run by GitHub Actions on every push to plugins/
"""
import json
import ast
import os
from pathlib import Path
from datetime import date

REPO = "SF12P/ophelia-plugins"
BASE_URL = f"https://raw.githubusercontent.com/{REPO}/main/plugins"

plugins_dir = Path("plugins")
entries = []

for py_file in sorted(plugins_dir.glob("*.py")):
    if py_file.name.startswith("_"):
        continue

    try:
        source = py_file.read_text(encoding="utf-8")
        tree   = ast.parse(source)

        # Extract module-level string assignments
        vals = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        key = target.id
                        try:
                            vals[key] = ast.literal_eval(node.value)
                        except Exception:
                            pass

        name = vals.get("NAME", py_file.stem)
        if not name:
            continue

        entry = {
            "name":         name,
            "display_name": vals.get("DISPLAY_NAME", name.replace("_"," ").title()),
            "description":  vals.get("DESCRIPTION", ""),
            "author":       vals.get("AUTHOR", "SF12P"),
            "version":      str(vals.get("VERSION", "1.0")),
            "tags":         vals.get("TAGS", []),
            "file":         py_file.name,
            "url":          f"{BASE_URL}/{py_file.name}",
            "requires":     vals.get("REQUIRES", []),
        }
        entries.append(entry)
        print(f"  Added: {name} v{entry['version']}")

    except Exception as e:
        print(f"  Skipped {py_file.name}: {e}")

index = {
    "version": "1.0",
    "updated": str(date.today()),
    "plugins": entries,
}

Path("index.json").write_text(
    json.dumps(index, indent=2), encoding="utf-8")
print(f"\nindex.json updated with {len(entries)} plugin(s).")
