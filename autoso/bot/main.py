# autoso/bot/main.py
import logging
from telegram.ext import Application, CommandHandler
from autoso.config import TELEGRAM_TOKEN
from autoso.bot.handlers import start_handler, texture_handler, bucket_handler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("texture", texture_handler))
    app.add_handler(CommandHandler("bucket", bucket_handler))
    app.run_polling()


if __name__ == "__main__":
    main()
