"""Point de chargement obligatoire, également après le lanceur natif Hermes."""
import os
import sys


def enforce():
    if os.environ.get("ARCIA_GOVERNANCE_REQUIRED") == "true":
        try:
            import runtime_guard
            runtime_guard.install()
        except BaseException:
            sys.stderr.write("ArcIA DLP : initialisation obligatoire impossible.\n")
            os._exit(78)
