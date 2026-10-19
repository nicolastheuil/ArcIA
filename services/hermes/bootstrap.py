"""Envelopper la commande existante sans remplacer les préférences de l'agent."""
import os
import sys
import sysconfig
from pathlib import Path
import runtime_guard

if os.environ.get("ARCIA_GOVERNANCE_REQUIRED") != "true" or not sys.argv[1:]:
    sys.stderr.write("ArcIA DLP : lancement non qualifié.\n")
    raise SystemExit(78)
anchor = Path(sysconfig.get_paths()["purelib"]) / "arcia_governance.pth"
if not anchor.is_file() or "arcia_required.enforce()" not in anchor.read_text():
    sys.stderr.write("ArcIA DLP : ancrage du lanceur natif absent.\n")
    raise SystemExit(78)
runtime_guard.install()
if not runtime_guard.INSTALLED:
    raise SystemExit(78)
os.execvp(sys.argv[1], sys.argv[1:])
