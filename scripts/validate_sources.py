#!/usr/bin/env python3
"""Local/CI structural validation using only public source and synthetic fixtures."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import harness

schema = json.loads((ROOT / "schemas/bootstrap.schema.json").read_text())
jsonschema.Draft202012Validator.check_schema(schema)
fixture = json.loads((ROOT / "examples/synthetic/instance.json").read_text())
jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(fixture)
for path in ROOT.rglob("*.yml"):
    list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
for path in ROOT.rglob("*.yaml"):
    list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
print("JSON_SCHEMA_AND_YAML_OK")
if sys.platform != "win32":
    lock = json.loads((ROOT / "versions.lock.yaml").read_text())
    with tempfile.TemporaryDirectory(prefix="arcia-synthetic-") as directory:
        inventory = Path(directory) / "inventory.json"
        inventory.write_text(json.dumps(harness.render(fixture, "a" * 64, lock)))
        for playbook in ("preflight.yml", "site.yml"):
            subprocess.run([str(Path(sys.executable).parent / "ansible-playbook"),
                            "-i", str(inventory), "--syntax-check", playbook],
                           cwd=ROOT / "infra/ansible", check=True)
        blocked = subprocess.run([str(Path(sys.executable).parent / "ansible-playbook"),
                                  "-i", str(inventory), "site.yml"],
                                 cwd=ROOT / "infra/ansible", capture_output=True, text=True)
        if blocked.returncode != 2 or "PLAY [Read-only Debian preflight]" in blocked.stdout:
            raise RuntimeError("BLOCKING_GATE_FAILED")
    print("ANSIBLE_SYNTAX_OK; NO_SSH_EXECUTED")
    print("ANSIBLE_SYNTHETIC_INSTALL_BLOCKED_BEFORE_SSH")
