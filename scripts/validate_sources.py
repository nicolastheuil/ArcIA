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
import hashlib
import re

schema = json.loads((ROOT / "schemas/bootstrap.schema.json").read_text())
jsonschema.Draft202012Validator.check_schema(schema)
fixture = json.loads((ROOT / "examples/synthetic/instance.json").read_text())
jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(fixture)
for path in ROOT.rglob("*.yml"):
    list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
for path in ROOT.rglob("*.yaml"):
    list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
print("JSON_SCHEMA_AND_YAML_OK")
lock = json.loads((ROOT / "versions.lock.yaml").read_text())
if 'vmware_foundation' in lock:
    vendor = ROOT/'deploy/vendor/vmware'
    expected_images = {image['pinned'] for image in lock['vmware_foundation']['images']}
    found_images = set()
    for name, source in lock['vmware_foundation']['sources'].items():
        content = (vendor/name).read_bytes()
        if hashlib.sha256(content).hexdigest() != source['rendered_sha256']:
            raise RuntimeError('VMWARE_MANIFEST_HASH_MISMATCH')
        found_images.update(re.findall(r'^\s*image:\s*(\S+)\s*$', content.decode(), re.M))
    if found_images != expected_images or not all(re.fullmatch(r'registry\.k8s\.io/[a-z0-9_./-]+@sha256:[a-f0-9]{64}', value) for value in found_images):
        raise RuntimeError('VMWARE_IMAGES_NOT_PINNED')
    print('VMWARE_MANIFEST_HASHES_AND_IMAGE_DIGESTS_OK; NOT_DEPLOYED')
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
