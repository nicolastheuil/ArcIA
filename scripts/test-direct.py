import json
import sys
sys.path.insert(0, r'C:\Users\NicolasTHEUIL\OneDrive - Arcitek\Projets\arcia\scripts')
import cluster_foundation

# Test loading the lock file
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
lock = json.loads((ROOT/'versions.lock.yaml').read_text())
print(f"Direct load: {lock['components']['k3s']['version']}")

# Test cluster_foundation install_k3s function (just the lock loading part)
print(f"ROOT: {ROOT}")
print(f"Lock file exists: {(ROOT/'versions.lock.yaml').is_file()}")