"""Handler para eliminar eventos — /eliminar."""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler

from calendar_service import CalendarService

logger = logging.getLogger(__name__)


async def eliminar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista los próximos eventos con botones para eliminar."""
    await update.message.reply_text("🔍 Cargando eventos...")

    try:
        cal = CalendarService()
        events = cal.get_upcoming_events(days=14)

        if not events:
            await update.message.reply_text(
                "📭 No hay eventos próximos para eliminar."
            )
            return

        # Guardar eventos en contexto para referencia
        context.user_data["eventos_para_eliminar"] = {
            event["id"]: event.get("summary", "Sin título") for event in events
        }

        keyboard = []
        for event in events[:15]:  # Máximo 15 botones
            summary = event.get("summary", "Sin título")
            start = event.get("start", {})
            if "dateTime" in start:
                from datetime import datetime
                dt = datetime.fromisoformat(start["dateTime"])
                date_str = dt.strftime("%d/%m %H:%M")
            elif "date" in start:
                date_str = start["date"]
            else:
                date_str = "?"

            label = f"🗑️ {summary} ({date_str})"
            # Truncar label si es muy largo
            if len(label) > 60:
                label = label[:57] + "..."

            keyboard.append([
                InlineKeyboardButton(label, callback_data=f"del_{event['id']}")
            ])

        keyboard.append([
            InlineKeyboardButton("❌ Cancelar", callback_data="del_cancelar")
        ])

        await update.message.reply_text(
            "🗑️ *¿Qué evento quieres eliminar?*\n\n"
            "Selecciona uno de la lista:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    except Exception as e:
        logger.error(f"Error listando eventos para eliminar: {e}")
        await update.message.reply_text(f"❌ Error: {e}")


async def confirmar_eliminacion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja la selección de evento para eliminar."""
    query = update.callback_query
    await query.answer()

    if query.data == "del_cancelar":
        await query.edit_message_text("❌ Eliminación cancelada.")
        return

    if query.data.startswith("del_confirm_"):
        # Confirmar eliminación
        event_id = query.data.replace("del_confirm_", "")
        try:
            cal = CalendarService()
            cal.delete_event(event_id)

            event_name = context.user_data.get("eventos_para_eliminar", {}).get(
                event_id, "evento"
            )
            await query.edit_message_text(
                f"✅ Evento *{event_name}* eliminado exitosamente.",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"Error eliminando evento: {e}")
            await query.edit_message_text(f"❌ Error al eliminar: {e}")
        return

    if query.data.startswith("del_"):
        # Pedir confirmación
        event_id = query.data.replace("del_", "")
        event_name = context.user_data.get("eventos_para_eliminar", {}).get(
            event_id, "este evento"
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    "✅ Sí, eliminar", callback_data=f"del_confirm_{event_id}"
                ),
                InlineKeyboardButton("❌ No", callback_data="del_cancelar"),
            ]
        ]

        await query.edit_message_text(
            f"⚠️ ¿Estás seguro de eliminar *{event_name}*?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


def get_delete_callback_handler() -> CallbackQueryHandler:
    """Devuelve el handler para callbacks de eliminación."""
    return CallbackQueryHandler(confirmar_eliminacion, pattern=r"^del_")
