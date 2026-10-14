"""
ArcIA Microsoft Teams Bot Adapter
Integrates Microsoft Teams (DM 1:1 and @ArcIA channel mentions) with LiteLLM / Hermes runtime.
"""
import os
import sys
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

SETTINGS = BotFrameworkAdapterSettings(APP_ID, APP_PASSWORD)
ADAPTER = BotFrameworkAdapter(SETTINGS)

async def call_litellm(user_message: str, user_name: str = "Collaborateur") -> str:
    """Dispatches user prompt to LiteLLM auto model (protected by Presidio DLP)."""
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "model": "auto",
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Tu es ArcIA, l'assistant et orchestrateur agentique d'entreprise d'Arcitek. "
                            "Réponds de façon synthétique, professionnelle et structurée en Markdown."
                        )
                    },
                    {"role": "user", "content": f"Message de {user_name}: {user_message}"}
                ]
            }
            async with session.post(f"{LITELLM_URL}/chat/completions", json=payload, timeout=aiohttp.ClientTimeout(total=45)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"]
                else:
                    err_text = await resp.text()
                    logger.error("LiteLLM returned %s: %s", resp.status, err_text)
                    return "⚠️ **ArcIA :** Erreur de communication avec la passerelle d'inférence d'entreprise."
    except Exception as e:
        logger.error("Error calling LiteLLM: %s", e)
        return "⚠️ **ArcIA :** La passerelle d'inférence est temporairement indisponible."

async def on_turn(turn_context: TurnContext):
    """Processes incoming Teams message activities."""
    activity = turn_context.activity

    if activity.type == ActivityTypes.message:
        text = activity.text or ""
        # Strip bot mention tag if in channel
        clean_text = text.replace("@ArcIA", "").strip()
        user_name = activity.from_property.name if activity.from_property else "Collaborateur"
        
        logger.info("Received message from %s: %s", user_name, clean_text)
        
        # Call LiteLLM inference
        reply_content = await call_litellm(clean_text, user_name)
        
        # Send reply
        reply = Activity(
            type=ActivityTypes.message,
            text=reply_content
        )
        await turn_context.send_activity(reply)

    elif activity.type == ActivityTypes.conversation_update:
        if activity.members_added:
            for member in activity.members_added:
                if member.id != activity.recipient.id:
                    welcome = (
                        "👋 **Bienvenue sur ArcIA !**\n\n"
                        "Je suis votre assistant IA agentique souverain. "
                        "Vous pouvez me poser des questions directement ici en DM ou me mentionner avec `@ArcIA` dans vos canaux d'équipe."
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
        return web.Response(status=500, text=str(e))

async def health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "service": "teams-bot-adapter", "version": "0.2.0"})

app = web.Application()
app.router.add_post("/api/teams/messages", messages)
app.router.add_get("/", health)
app.router.add_get("/health", health)
app.router.add_get("/healthz", health)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=3978)
