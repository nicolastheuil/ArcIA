"""Classification commune au wizard et à la projection d'avatars."""
import hashlib
import json

ICONS = {
    "default": "/static/icon-model-default.svg",
    "zdr": "/static/icon-model-zdr.svg",
    "local": "/static/icon-model-local.svg",
}


def enabled(value):
    return value is True or (isinstance(value, str) and value.strip().lower() == "true")


def resolve_model_icon(model, custom_providers=()):
    provider = str(model.get("provider") or "").lower()
    custom = next((p for p in custom_providers if p.get("id") == provider), {})
    hosting = model.get("hosting") or custom.get("hosting")
    local = hosting == "local" or (hosting != "cloud" and provider in {"local", "ollama", "vllm", "local_vllm"})
    kind = "local" if local else "zdr" if enabled(model.get("zdr")) else "default"
    badge = {"local": "Liseret doré (Local souverain)", "zdr": "Liseret argenté (Cloud ZDR)", "default": "aIA classique"}[kind]
    return {"type": kind, "icon": ICONS[kind], "badge": badge}


def build_mapping(cfg):
    gateway = cfg.get("llm_gateway", {})
    mappings = gateway.get("models_routing") or []
    models = {}
    for model in mappings:
        model_id = str(model.get("alias") or model.get("name") or "").strip()
        if model_id:
            models[model_id] = resolve_model_icon(model, gateway.get("custom_providers") or [])
    result = {"models": models, "default_icon": ICONS["default"], "local_icon": ICONS["local"], "zdr_icon": ICONS["zdr"]}
    result["revision"] = hashlib.sha256(json.dumps(result, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return result


def projected_icon(model_id, mapping, visible_ids):
    """Aucune projection pour un modèle invisible, inconnu ou un chemin non approuvé."""
    if model_id not in visible_ids:
        return None
    icon = mapping.get("models", {}).get(model_id, {}).get("icon")
    return icon if icon in ICONS.values() else None
