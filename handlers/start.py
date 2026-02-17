"""Handler para el comando /start."""

import logging
from telegram import Update
from telegram.ext import ContextTypes

import config

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el comando /start — bienvenida e información del bot."""
    user = update.effective_user
    user_id = user.id

    welcome = (
        f"👋 ¡Hola {user.first_name}!\n\n"
        "Soy tu **asistente de agenda** 📅\n"
        "Estoy conectado a tu Google Calendar y puedo ayudarte a:\n\n"
        "✅ **Crear eventos** — envíame un mensaje como:\n"
        '   _"Reunión con Juan mañana a las 3pm"_\n'
        '   _"Dentista el viernes a las 10"_\n\n'
        "📋 **Ver tu agenda** — /agenda o /hoy\n"
        "🗑️ **Eliminar eventos** — /eliminar\n"
        "✔️ **Completar tareas** — /completar\n"
        "➕ **Crear paso a paso** — /nuevo\n\n"
        "⏰ **Recordatorios automáticos** cada 2 horas (6:30 a 00:00)\n"
        "🔄 Las tareas no completadas se renuevan al día siguiente\n\n"
        "También puedes escribirme en lenguaje natural y yo interpreto lo que necesitas.\n\n"
        f"🔑 Tu ID de usuario: `{user_id}`\n"
    )

    if config.AUTHORIZED_USER_ID and str(user_id) != config.AUTHORIZED_USER_ID:
        welcome += (
            "\n⚠️ *No estás autorizado para usar este bot.*\n"
            f"Configurá `AUTHORIZED_USER_ID={user_id}` en el archivo `.env`"
        )

    await update.message.reply_text(welcome, parse_mode="Markdown")
