"""Bot de Telegram — Asistente de Agenda con Google Calendar.

Entry point principal. Registra handlers y arranca polling.
"""

import logging
import sys

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
)

import config
from handlers.start import start_command
from handlers.create_event import get_create_event_handler
from handlers.list_events import agenda_command, hoy_command
from handlers.delete_event import eliminar_command, get_delete_callback_handler
from handlers.complete_event import completar_command, get_completar_callback_handler
from handlers.natural_language import handle_natural_language, get_nlp_callback_handler
from handlers.voice import handle_voice
from reminder_scheduler import setup_reminders

# Configurar logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def check_authorized(func):
    """Decorator para verificar que el usuario esté autorizado."""
    async def wrapper(update, context):
        if config.AUTHORIZED_USER_ID:
            user_id = str(update.effective_user.id)
            if user_id != config.AUTHORIZED_USER_ID:
                await update.message.reply_text(
                    "⛔ No estás autorizado para usar este bot."
                )
                return
        return await func(update, context)
    return wrapper


def main():
    """Arranca el bot."""
    # Validaciones
    if not config.TELEGRAM_BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN no configurado en .env")
        sys.exit(1)

    if not config.GEMINI_API_KEY:
        logger.error("❌ GEMINI_API_KEY no configurado en .env")
        sys.exit(1)

    logger.info("🚀 Iniciando bot de agenda...")

    # Crear aplicación
    app = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).build()

    # === Registrar handlers ===

    # Conversación para crear evento paso a paso (tiene prioridad)
    app.add_handler(get_create_event_handler())

    # Comandos simples
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("agenda", check_authorized(agenda_command)))
    app.add_handler(CommandHandler("hoy", check_authorized(hoy_command)))
    app.add_handler(CommandHandler("eliminar", check_authorized(eliminar_command)))
    app.add_handler(CommandHandler("completar", check_authorized(completar_command)))

    # Callbacks de botones inline
    app.add_handler(get_delete_callback_handler())
    app.add_handler(get_completar_callback_handler())
    app.add_handler(get_nlp_callback_handler())

    # Mensajes de texto libre → NLP (va último, catch-all)
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            check_authorized(handle_natural_language),
        )
    )

    # Mensajes de voz
    app.add_handler(
        MessageHandler(
            filters.VOICE,
            check_authorized(handle_voice),
        )
    )

    # === Configurar recordatorios periódicos ===
    setup_reminders(app)

    # Arrancar
    logger.info("✅ Bot listo. Esperando mensajes...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
