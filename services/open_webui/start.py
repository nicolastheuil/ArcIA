"""Lance le backend officiel avec la projection ArcIA et sa clé de session persistante."""
import os
import hashlib
import hmac
from pathlib import Path
import secrets
import sys


def main():
    # L'image officielle place le backend dans son WORKDIR, distinct du lanceur monté.
    sys.path.insert(0, str(Path.cwd()))
    if not os.environ.get("WEBUI_SECRET_KEY"):
        key_file = Path(os.environ.get("WEBUI_SECRET_KEY_FILE", "/app/backend/data/.webui_secret_key"))
        key_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(secrets.token_urlsafe(48))
        os.environ["WEBUI_SECRET_KEY"] = key_file.read_text(encoding="utf-8").strip()
        if not os.environ["WEBUI_SECRET_KEY"]:
            raise RuntimeError("Clé de session persistante vide ; démarrage interrompu.")
    if os.environ.get("ARCIA_HERMES_FILES_ENABLED") == "true":
        os.environ["ARCIA_HERMES_FILES_KEY"] = hmac.new(
            os.environ["WEBUI_SECRET_KEY"].encode(), b"arcia-hermes-files-internal-v1", hashlib.sha256).hexdigest()
        os.environ["OPENAI_API_KEYS"] = os.environ["OPENAI_API_KEYS"].replace(
            "__ARCIA_HERMES_FILES_KEY__", os.environ["ARCIA_HERMES_FILES_KEY"])
    import uvicorn
    uvicorn.run("arcia_webui:app", host=os.environ.get("HOST", "0.0.0.0"),
                port=int(os.environ.get("PORT", "8080")), workers=int(os.environ.get("UVICORN_WORKERS", "1")),
                forwarded_allow_ips=os.environ.get("FORWARDED_ALLOW_IPS", "*"))


if __name__ == "__main__":
    main()
