"""
ArcIA Microsoft Teams Bot Adapter
Integrates Microsoft Teams (DM 1:1 and @ArcIA channel mentions) with LiteLLM (simple/*) and Hermes Agent (agentic/*).
"""
import os
import re
import logging
import traceback
import unicodedata
from aiohttp import web
from botbuilder.core import (
    BotFrameworkAdapter,
    BotFrameworkAdapterSettings,
    TurnContext,
)
from botbuilder.schema import Activity, ActivityTypes
from botframework.connector.auth import AuthenticationConfiguration
import aiohttp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("arcia-teams-bot")

APP_ID = os.environ.get("MICROSOFT_APP_ID", "").strip()
APP_PASSWORD = os.environ.get("MICROSOFT_APP_PASSWORD", "").strip()
APP_TENANT_ID = os.environ.get("MICROSOFT_APP_TENANT_ID", os.environ.get("TEAMS_BOT_TENANT_ID", "")).strip()
LITELLM_URL = os.environ.get("LITELLM_URL", "http://litellm-proxy.arcia.svc:4000/v1").rstrip("/")
LITELLM_API_KEY = os.environ.get("LITELLM_API_KEY", "")
HERMES_URL = os.environ.get("HERMES_URL", "http://hermes-studio.arcia.svc:8642/v1").rstrip("/")
HERMES_API_KEY = os.environ.get("HERMES_API_KEY", LITELLM_API_KEY)
DEFAULT_MODEL = os.environ.get("TEAMS_DEFAULT_MODEL", "simple/auto")
SYSTEM_PROMPT = os.environ.get(
    "TEAMS_SYSTEM_PROMPT",
    "Tu es ArcIA, l'assistant et orchestrateur agentique d'entreprise. "
    "Réponds de façon synthétique, professionnelle et structurée en Markdown."
)

auth_config = AuthenticationConfiguration(tenant_id=APP_TENANT_ID) if APP_TENANT_ID else AuthenticationConfiguration()
SETTINGS = BotFrameworkAdapterSettings(
    app_id=APP_ID,
    app_password=APP_PASSWORD,
    channel_auth_tenant=APP_TENANT_ID or None,
    auth_configuration=auth_config,
)
ADAPTER = BotFrameworkAdapter(SETTINGS)


def sanitize_user_email(user_name: str) -> str:
    """Normalise le nom d'utilisateur en une adresse email ASCII valide sans caractères accentués."""
    normalized = unicodedata.normalize("NFKD", user_name).encode("ASCII", "ignore").decode("ASCII")
    clean = re.sub(r"[^a-zA-Z0-9._-]", ".", normalized).strip(".").lower()
    return f"{clean or 'collaborateur'}@teams.local"


def clean_user_text(raw_text: str) -> str:
    """Nettoie le texte reçu depuis Teams : balises XML de mention, tags HTML et espaces superflus."""
    if not raw_text:
        return ""
    # 1. Supprime les balises de mention XML Teams (<at>ArcIA</at> ou <at id="...">...</at>)
    cleaned = re.sub(r"<at[^>]*>.*?</at>", "", raw_text, flags=re.IGNORECASE)
    # 2. Supprime les balises HTML injectées par l'éditeur riche de Teams (<p>, <br>, <div>, etc.)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    # 3. Supprime les mentions textuelles résiduelles
    cleaned = cleaned.replace("@ArcIA", "")
    return " ".join(cleaned.split())


async def handle_builtin_commands(clean_text: str) -> str | None:
    """Intercepte les commandes utilitaires locales (aide, statut) sans consommer de tokens d'inférence."""
    cmd = clean_text.lower()
    if cmd in ("aide", "help", "/aide", "/help", "?"):
        return (
            "🤖 **ArcIA — Assistant IA Souverain d'Entreprise**\n\n"
            "Je suis votre assistant agentique souverain directement intégré dans Microsoft Teams :\n\n"
            "- 💬 **Mode Discussion Rapide** : Posez directement votre question pour une réponse synthétique via LiteLLM (`simple/auto`).\n"
            "- 🚀 **Mode Mission Agentique** : Préfixez votre message par `/agent <mission>` ou `/hermes <mission>` pour activer le moteur agentique Hermes (`agentic/auto`) et exécuter une tâche outillée autonome.\n"
            "- 🛡️ **Double Barrière DLP** : Vos échanges sont protégés en amont et en aval par le bouclier Microsoft Presidio (caviardage PII et secrets, Zéro Rétention de Données).\n"
            "- 📊 **Statut du Service** : Tapez `statut` pour tester la disponibilité opérationnelle des composants.\n\n"
            "*Exemples :*\n"
            "- `Explique-moi la différence entre chiffrement asymétrique et symétrique.`\n"
            "- `/agent Synthétise le statut des déploiements et liste les actions recommandées.`"
        )

    if cmd in ("statut", "status", "/statut", "/status"):
        litellm_ok = False
        try:
            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": f"Bearer {LITELLM_API_KEY}"} if LITELLM_API_KEY else {}
                async with session.get(f"{LITELLM_URL}/health/readiness", headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    litellm_ok = resp.status in (200, 204)
        except Exception:
            litellm_ok = False

        status_icon = "🟢" if litellm_ok else "🔴"
        return (
            f"📊 **Statut Opérationnel d'ArcIA**\n\n"
            f"- **Adaptateur Teams Bot** : 🟢 Opérationnel (v0.4.0)\n"
            f"- **Passerelle LiteLLM Proxy** : {status_icon} ({'En ligne' if litellm_ok else 'Indisponible'})\n"
            f"- **Profil Inférence Défaut** : `{DEFAULT_MODEL}`\n"
            f"- **Profil Agentique Hermes** : `agentic/auto`\n"
            f"- **Sécurité DLP** : 🛡️ Double Barrière Presidio Fail-Closed Active\n"
            f"- **Mode Tenant Azure** : `{'Single-Tenant (' + APP_TENANT_ID[:8] + '...)' if APP_TENANT_ID else 'Multi-Tenant'}`"
        )

    return None


async def call_inference(user_message: str, user_name: str = "Collaborateur") -> str:
    """Dispatches user prompt to LiteLLM (simple/auto) or Hermes (agentic/auto if prefixed with /agent or /hermes)."""
    agent_prefixes = ("/agent ", "!agent ", "/hermes ", "!hermes ")
    use_agent = False
    clean_prompt = user_message

    for prefix in agent_prefixes:
        if user_message.lower().startswith(prefix):
            use_agent = True
            clean_prompt = user_message[len(prefix):].strip()
            break

    if use_agent:
        target_url = HERMES_URL
        api_key = HERMES_API_KEY
        model = "agentic/auto"
    else:
        target_url = LITELLM_URL
        api_key = LITELLM_API_KEY
        model = DEFAULT_MODEL

    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT
                    },
                    {"role": "user", "content": f"Message de {user_name}: {clean_prompt}"}
                ]
            }
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            headers["X-OpenWebUI-User-Email"] = sanitize_user_email(user_name)

            async with session.post(
                f"{target_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"]
                else:
                    err_text = await resp.text()
                    logger.error("Inference gateway (%s at %s) returned %s: %s", model, target_url, resp.status, err_text)
                    return "⚠️ **ArcIA :** Erreur de communication avec la passerelle d'inférence d'entreprise."
    except Exception as e:
        logger.error("Error calling inference gateway (%s at %s): %s", model, target_url, e)
        return "⚠️ **ArcIA :** La passerelle d'inférence est temporairement indisponible."


async def on_turn(turn_context: TurnContext):
    """Processes incoming Teams message activities."""
    activity = turn_context.activity

    if activity.type == ActivityTypes.message:
        raw_text = activity.text or ""
        clean_text = clean_user_text(raw_text)
        user_name = activity.from_property.name if activity.from_property else "Collaborateur"

        logger.info("Received message from %s (cleaned length: %d chars)", user_name, len(clean_text))

        if not clean_text:
            return

        # Vérification des commandes intégrées (aide, statut)
        builtin_reply = await handle_builtin_commands(clean_text)
        if builtin_reply:
            reply = Activity(type=ActivityTypes.message, text=builtin_reply)
            await turn_context.send_activity(reply)
            return

        reply_content = await call_inference(clean_text, user_name)
        reply = Activity(type=ActivityTypes.message, text=reply_content)
        await turn_context.send_activity(reply)

    elif activity.type == ActivityTypes.conversation_update:
        if activity.members_added:
            for member in activity.members_added:
                if member.id != activity.recipient.id:
                    welcome = (
                        "👋 **Bienvenue sur ArcIA !**\n\n"
                        "Je suis votre assistant IA agentique souverain d'entreprise.\n\n"
                        "- Posez une question directe (`simple/auto`) ou préfixez par `/agent` pour activer le runtime Hermes (`agentic/auto`).\n"
                        "- Tapez `aide` à tout moment pour afficher la liste des commandes.\n"
                        "- Mentionnez `@ArcIA` dans vos canaux d'équipe."
                    )
                    await turn_context.send_activity(Activity(type=ActivityTypes.message, text=welcome))


async def messages(request: web.Request) -> web.Response:
    """Webhook endpoint for Microsoft Bot Framework."""
    if "application/json" in request.headers.get("Content-Type", ""):
        body = await request.json()
    else:
        return web.Response(status=415)

    activity = Activity().deserialize(body)
    auth_header = request.headers.get("Authorization", "")

    try:
        response = await ADAPTER.process_activity(activity, auth_header, on_turn)
        if response:
            return web.json_response(data=response.body, status=response.status)
        return web.Response(status=200)
    except Exception as e:
        logger.error("Exception in messages handler: %s\n%s", e, traceback.format_exc())
        return web.Response(status=500, text=f"Internal Bot Framework Error: {e}")


async def messages_info(request: web.Request) -> web.Response:
    return web.json_response({
        "status": "ready",
        "service": "arcia-teams-bot-adapter",
        "endpoint": "/api/teams/messages",
        "default_model": DEFAULT_MODEL,
        "agentic_model": "agentic/auto",
        "tenant_mode": f"single-tenant ({APP_TENANT_ID})" if APP_TENANT_ID else "multi-tenant",
        "note": "Microsoft Bot Framework Messaging Endpoint (POST required for Bot Activities)"
    })


async def health(request: web.Request) -> web.Response:
    return web.json_response({
        "status": "ok",
        "service": "teams-bot-adapter",
        "version": "0.4.0",
        "default_model": DEFAULT_MODEL,
        "tenant_mode": "single-tenant" if APP_TENANT_ID else "multi-tenant"
    })


app = web.Application()
# Routes universelles Teams (/api/messages) et spécifiques ArcIA (/api/teams/messages)
app.router.add_post("/api/messages", messages)
app.router.add_post("/api/messages/", messages)
app.router.add_get("/api/messages", messages_info)
app.router.add_get("/api/messages/", messages_info)
app.router.add_post("/api/teams/messages", messages)
app.router.add_post("/api/teams/messages/", messages)
app.router.add_get("/api/teams/messages", messages_info)
app.router.add_get("/api/teams/messages/", messages_info)
app.router.add_get("/", health)
app.router.add_get("/health", health)
app.router.add_get("/healthz", health)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=3978)

