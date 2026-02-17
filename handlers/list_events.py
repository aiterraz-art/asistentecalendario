"""Handlers para listar eventos — /agenda y /hoy."""

import logging
from telegram import Update
from telegram.ext import ContextTypes

from calendar_service import CalendarService, format_event

logger = logging.getLogger(__name__)


async def agenda_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra los eventos de los próximos 7 días."""
    await update.message.reply_text("🔍 Buscando eventos de la semana...")

    try:
        cal = CalendarService()
        events = cal.get_upcoming_events(days=7)

        if not events:
            await update.message.reply_text(
                "📭 No tienes eventos en los próximos 7 días.\n"
                "Usa /nuevo para crear uno o simplemente escríbeme."
            )
            return

        lines = ["📅 *Tu agenda de los próximos 7 días:*\n"]
        for event in events:
            lines.append(format_event(event))

        await update.message.reply_text(
            "\n\n".join(lines),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Error listando agenda: {e}")
        await update.message.reply_text(f"❌ Error al obtener la agenda: {e}")


async def hoy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra los eventos de hoy."""
    await update.message.reply_text("🔍 Buscando eventos de hoy...")

    try:
        cal = CalendarService()
        events = cal.get_today_events()

        if not events:
            await update.message.reply_text(
                "📭 No tienes eventos para hoy.\n"
                "¡Día libre! 🎉"
            )
            return

        lines = [f"📅 *Eventos de hoy* ({len(events)}):\n"]
        for event in events:
            lines.append(format_event(event))

        await update.message.reply_text(
            "\n\n".join(lines),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Error listando eventos de hoy: {e}")
        await update.message.reply_text(f"❌ Error al obtener eventos: {e}")
