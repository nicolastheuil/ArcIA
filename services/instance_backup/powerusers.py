"""État désiré des instances dédiées, inclus uniquement dans le bundle chiffré.

Ces déclarations recréent les ressources et identifiants, jamais les données des
PVC. Une instance historique présente seulement sur le cluster doit d'abord
être exportée par son administrateur ; aucune découverte implicite n'a lieu.
"""
import copy
import json
import re


_FIELDS = {"email", "team", "job_title", "manager", "storage_size", "custom_soul",
           "vpn", "pat", "password", "replicas"}


def _slug(email):
    # Même transformation déterministe que scripts/arcia_poweruser.email_to_slug,
    # sans son fallback aléatoire : une sauvegarde ne crée jamais d'identité.
    if not isinstance(email, str) or not re.fullmatch(r"[^\s@]+@[^\s@]+", email):
        raise ValueError("Adresse du Power User invalide.")
    slug = re.sub(r"-+", "-", re.sub(r"[^a-z0-9\-]", "-", email.split("@")[0].lower())).strip("-")[:40]
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", slug):
        raise ValueError("Identifiant du Power User non déterministe.")
    return slug


def _record(record):
    if not isinstance(record, dict) or set(record) - _FIELDS:
        raise ValueError("Déclaration Power User invalide.")
    result = dict(team="engineering", job_title="Expert / Ingénieur",
                  manager="Direction Technique", storage_size="10Gi",
                  custom_soul=None, vpn=False, replicas=1)
    result.update(record)
    _slug(result.get("email"))
    for field in ("team", "job_title", "manager", "pat", "password"):
        value = result.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Déclaration Power User incomplète ; identifiants existants requis.")
    if not isinstance(result["storage_size"], str) or not re.fullmatch(r"[1-9]\d*(?:Mi|Gi|Ti)", result["storage_size"]):
        raise ValueError("Capacité du Power User invalide.")
    if result["custom_soul"] is not None and not isinstance(result["custom_soul"], str):
        raise ValueError("Personnalité du Power User invalide.")
    if type(result["vpn"]) is not bool or type(result["replicas"]) is not int or result["replicas"] not in (0, 1):
        raise ValueError("État du Power User invalide ; un seul propriétaire actif autorisé.")
    return result


def declared_powerusers(cfg):
    """Valider toutes les déclarations sans lire le cluster ni le disque local."""
    section = cfg.get("powerusers", {})
    if not isinstance(section, dict) or not isinstance(section.get("instances", {}), dict):
        raise ValueError("Déclarations Power Users invalides.")
    result, pats = {}, set()
    for slug, record in section.get("instances", {}).items():
        normalized = _record(record)
        if slug != _slug(normalized["email"]):
            raise ValueError("Identifiant déclaré incohérent avec le Power User.")
        if normalized["pat"] in pats:
            raise ValueError("Chaque Power User doit posséder son propre PAT.")
        pats.add(normalized["pat"])
        result[slug] = normalized
    return result


def register_poweruser(cfg, record):
    """Enregistrer les identifiants effectifs après un provisionnement réussi."""
    records = declared_powerusers(cfg)
    record = _record(record)
    slug = _slug(record["email"])
    if slug in records and records[slug]["email"].lower() != record["email"].lower():
        raise ValueError("Cet identifiant appartient déjà à un autre Power User.")
    if any(other != slug and data["pat"] == record["pat"] for other, data in records.items()):
        raise ValueError("Chaque Power User doit posséder son propre PAT.")
    records[slug] = record
    cfg.setdefault("powerusers", {})["instances"] = records
    return slug


def update_poweruser(cfg, slug, **changes):
    """Modifier l'état désiré existant ; ne jamais inventer un utilisateur legacy."""
    records = declared_powerusers(cfg)
    if slug not in records:
        return False
    record = _record(dict(records[slug], **changes))
    if _slug(record["email"]) != slug or record["email"].lower() != records[slug]["email"].lower():
        raise ValueError("L'identité d'un Power User déclaré ne peut pas être remplacée.")
    if any(other != slug and data["pat"] == record["pat"] for other, data in records.items()):
        raise ValueError("Chaque Power User doit posséder son propre PAT.")
    records[slug] = record
    cfg["powerusers"]["instances"] = records
    return True


def remove_poweruser(cfg, slug):
    """Retirer une déclaration après suppression effective des ressources."""
    records = declared_powerusers(cfg)
    if slug not in records:
        return False
    del records[slug]
    cfg["powerusers"]["instances"] = records
    return True


def _pat_registration_code(slug, record):
    # JSON sérialisé dans un littéral Python : aucune interpolation de code à
    # partir des identifiants, aucune valeur secrète dans argv ou les sorties.
    payload = json.dumps({"key": record["pat"], "key_alias": "pat-" + slug,
                          "user_id": record["email"], "max_budget": 200.0})
    return "payload = json.loads(" + repr(payload) + ")\n" + _PAT_SCRIPT


_PAT_SCRIPT = '''import hashlib, os, sys, urllib.parse, urllib.request
def request(path, data=None):
    req = urllib.request.Request('http://127.0.0.1:4000' + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers={'Authorization': 'Bearer ' + os.environ['LITELLM_MASTER_KEY'],
                 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)
def present():
    digest = hashlib.sha256(payload['key'].encode()).hexdigest()
    result = request('/key/list?' + urllib.parse.urlencode({
        'return_full_object': 'true', 'key_hash': digest}))
    if not isinstance(result, dict) or not isinstance(result.get('keys'), list):
        raise ValueError()
    for key in result['keys']:
        if isinstance(key, dict) and key.get('token') == digest:
            if key.get('user_id') != payload['user_id'] or key.get('key_alias') != payload['key_alias']:
                raise ValueError()
            return True
    return False
try:
    if not present():
        request('/key/generate', payload)
        if not present():
            raise ValueError()
except Exception:
    print('ARCIA_POWERUSER_PAT_FAILED', file=sys.stderr)
    sys.exit(1)
'''


def reconcile_powerusers(cfg, runner, dry_run=False):
    """Réappliquer les déclarations avec K8sRunner, sans générer de credentials.

    La suspension est projetée directement dans le manifeste, sans démarrer
    brièvement un agent en veille. Le retour compte les applications acceptées,
    pas des pods prêts ni une restauration de données. Les erreurs du runner
    sont volontairement masquées car elles peuvent contenir le Secret appliqué.
    """
    records = declared_powerusers(cfg)
    if not records:
        return 0
    namespace = cfg.get("kubernetes", {}).get("namespace", "arcia")
    fqdn = cfg.get("network", {}).get("public_fqdn", "assistant.example.org")
    if not isinstance(namespace, str) or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", namespace):
        raise ValueError("Namespace des Power Users invalide.")
    if not isinstance(fqdn, str) or not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?", fqdn):
        raise ValueError("Hôte public des Power Users invalide.")
    from scripts.arcia_poweruser import render_manifest
    from scripts.hermes_files import declared_users
    protected_slugs = {user["poweruser_slug"] for user in declared_users(cfg) if user.get("poweruser_slug")}
    # Préparer tous les manifestes avant la première mutation externe.
    manifests = []
    for slug, record in sorted(records.items()):
        manifest = render_manifest(user_email=record["email"], team=record["team"],
            job_title=record["job_title"], manager=record["manager"],
            custom_soul=record["custom_soul"], storage_size=record["storage_size"],
            public_fqdn=fqdn, namespace=namespace, litellm_pat=record["pat"],
            studio_password=record["password"], enable_vpn=record["vpn"],
            config=copy.deepcopy(cfg), replicas=record["replicas"])
        manifests.append((slug, record, manifest))
    if dry_run:
        return len(manifests)
    for slug, record, manifest in manifests:
        try:
            existing = False
            if slug in protected_slugs:
                rc, output, _ = runner.run(["get", "deployment", "hermes-poweruser-" + slug, "-n", namespace,
                                            "--ignore-not-found", "-o", "json"], timeout=20)
                if rc:
                    raise RuntimeError()
                existing = bool(output.strip())
                if existing and json.loads(output).get("metadata", {}).get("name") != "hermes-poweruser-" + slug:
                    raise RuntimeError()
            if not existing:
                rc, _, _ = runner.run(["apply", "-f", "-"], stdin_input=manifest)
                if rc:
                    raise RuntimeError()
            rc, _, _ = runner.run(["exec", "-i", "deployment/litellm-proxy", "-n", namespace,
                                   "--", "python3"],
                                  stdin_input="import json\n" + _pat_registration_code(slug, record), timeout=60)
            if rc:
                raise RuntimeError()
        except Exception:
            raise RuntimeError("Réapplication Power User incomplète ; vérifier les ressources et l'enregistrement PAT localement.") from None
    return len(manifests)
