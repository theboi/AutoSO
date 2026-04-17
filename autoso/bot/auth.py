# autoso/bot/auth.py
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
import autoso.config as config

_UNAUTH_MESSAGE = "Unauthorised. Contact the bot administrator to request access."


def require_auth(handler):
    @wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id not in config.WHITELISTED_USER_IDS:
            # update.message is None for callback queries and inline queries
            if update.message:
                await update.message.reply_text(_UNAUTH_MESSAGE)
            elif update.effective_chat:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=_UNAUTH_MESSAGE,
                )
            return
        return await handler(update, context)
    return wrapper
