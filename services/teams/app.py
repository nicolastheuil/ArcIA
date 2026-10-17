"""
ArcIA Microsoft Teams Bot Adapter
Integrates Microsoft Teams (DM 1:1 and @ArcIA channel mentions) with LiteLLM (simple/*) and Hermes Agent (agentic/*).
"""
import os
import logging
from aiohttp import web
from botbuilder.core import (
    BotFrameworkAdapter,
    BotFrameworkAdapterSettings,
    TurnContext,
)
from botbuilder.schema import Activity, ActivityTypes
import aiohttp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("arcia-teams-bot")

APP_ID = os.environ.get("MICROSOFT_APP_ID", "")
APP_PASSWORD = os.environ.get("MICROSOFT_APP_PASSWORD", "")
LITELLM_URL = os.environ.get("LITELLM_URL", "http://litellm-proxy.arcia.svc:4000/v1")
LITELLM_API_KEY = os.environ.get("LITELLM_API_KEY", "")
HERMES_URL = os.environ.get("HERMES_URL", "http://hermes-studio.arcia.svc:8642/v1")
HERMES_API_KEY = os.environ.get("HERMES_API_KEY", LITELLM_API_KEY)
DEFAULT_MODEL = os.environ.get("TEAMS_DEFAULT_MODEL", "simple/auto")

SETTINGS = BotFrameworkAdapterSettings(APP_ID, APP_PASSWORD)
ADAPTER = BotFrameworkAdapter(SETTINGS)


async def call_inference(user_message: str, user_name: str = "Collaborateur") -> str:
    """Dispatches user prompt to LiteLLM (simple/auto) or Hermes (agentic/auto if prefixed with /agent)."""
    use_agent = user_message.lower().startswith("/agent ")
    if use_agent:
        clean_prompt = user_message[7:].strip()
        target_url = HERMES_URL
        api_key = HERMES_API_KEY
        model = "agentic/auto"
    else:
        clean_prompt = user_message
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
                        "content": (
                            "Tu es ArcIA, l'assistant et orchestrateur agentique d'entreprise. "
                            "Réponds de façon synthétique, professionnelle et structurée en Markdown."
                        )
                    },
                    {"role": "user", "content": f"Message de {user_name}: {clean_prompt}"}
                ]
            }
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            headers["X-OpenWebUI-User-Email"] = f"{user_name.lower().replace(' ', '.')}@teams.local"

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
                    logger.error("Inference gateway (%s) returned %s: %s", model, resp.status, err_text)
                    return "⚠️ **ArcIA :** Erreur de communication avec la passerelle d'inférence d'entreprise."
    except Exception as e:
        logger.error("Error calling inference gateway: %s", e)
        return "⚠️ **ArcIA :** La passerelle d'inférence est temporairement indisponible."


async def on_turn(turn_context: TurnContext):
    """Processes incoming Teams message activities."""
    activity = turn_context.activity

    if activity.type == ActivityTypes.message:
        text = activity.text or ""
        clean_text = text.replace("@ArcIA", "").strip()
        user_name = activity.from_property.name if activity.from_property else "Collaborateur"

        logger.info("Received message from %s (length: %d chars)", user_name, len(clean_text))
        reply_content = await call_inference(clean_text, user_name)

        reply = Activity(type=ActivityTypes.message, text=reply_content)
        await turn_context.send_activity(reply)

    elif activity.type == ActivityTypes.conversation_update:
        if activity.members_added:
            for member in activity.members_added:
                if member.id != activity.recipient.id:
                    welcome = (
                        "👋 **Bienvenue sur ArcIA !**\n\n"
                        "Je suis votre assistant IA agentique souverain.\n"
                        "- Posez une question directe (`simple/auto`) ou préfixez par `/agent` pour activer le moteur agentique Hermes (`agentic/auto`).\n"
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
        logger.error("Exception in messages handler: %s", e)
        return web.Response(status=500, text="Internal Bot Framework Error")


async def messages_info(request: web.Request) -> web.Response:
    return web.json_response({
        "status": "ready",
        "service": "arcia-teams-bot-adapter",
        "endpoint": "/api/teams/messages",
        "default_model": DEFAULT_MODEL,
        "agentic_model": "agentic/auto",
        "note": "Microsoft Bot Framework Messaging Endpoint (POST required for Bot Activities)"
    })


async def health(request: web.Request) -> web.Response:
    return web.json_response({
        "status": "ok",
        "service": "teams-bot-adapter",
        "version": "0.4.0",
        "default_model": DEFAULT_MODEL
    })


app = web.Application()
app.router.add_post("/api/teams/messages", messages)
app.router.add_get("/api/teams/messages", messages_info)
app.router.add_get("/", health)
app.router.add_get("/health", health)
app.router.add_get("/healthz", health)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=3978)
