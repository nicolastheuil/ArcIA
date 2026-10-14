import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
lock = json.loads((ROOT/'versions.lock.yaml').read_text())
print("K3s version:", lock['components']['k3s']['version'])
print("K3s installer_url:", lock['components']['k3s']['installer_url'])
print("K3s binary_url:", lock['components']['k3s']['binary_url'])
print("K3s images_url:", lock['components']['k3s']['images_url'])