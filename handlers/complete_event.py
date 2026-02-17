"""Handler para marcar tareas como completadas — /completar."""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler

from calendar_service import CalendarService
from reminder_scheduler import COMPLETED_MARKER

logger = logging.getLogger(__name__)


async def completar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista los eventos de hoy para marcar como completados."""
    await update.message.reply_text("🔍 Cargando tareas de hoy...")

    try:
        cal = CalendarService()
        events = cal.get_today_events()

        # Filtrar solo pendientes (no completadas)
        pending = [
            e for e in events
            if COMPLETED_MARKER not in e.get("description", "")
        ]

        if not pending:
            await update.message.reply_text(
                "✅ ¡No tienes tareas pendientes hoy! Todo completado. 🎉"
            )
            return

        context.user_data["eventos_completar"] = {
            e["id"]: e.get("summary", "Sin título") for e in pending
        }

        keyboard = []
        for event in pending:
            summary = event.get("summary", "Sin título")
            label = f"✅ {summary}"
            if len(label) > 60:
                label = label[:57] + "..."
            keyboard.append([
                InlineKeyboardButton(label, callback_data=f"comp_{event['id']}")
            ])

        keyboard.append([
            InlineKeyboardButton("❌ Cancelar", callback_data="comp_cancelar")
        ])

        await update.message.reply_text(
            f"📋 *Tareas pendientes hoy* ({len(pending)}):\n\n"
            "¿Cuál completaste?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    except Exception as e:
        logger.error(f"Error listando tareas para completar: {e}")
        await update.message.reply_text(f"❌ Error: {e}")


async def confirmar_completar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback para marcar tarea como completada."""
    query = update.callback_query
    await query.answer()

    if query.data == "comp_cancelar":
        await query.edit_message_text("❌ Cancelado.")
        return

    if query.data.startswith("comp_"):
        event_id = query.data.replace("comp_", "")
        event_name = context.user_data.get("eventos_completar", {}).get(
            event_id, "tarea"
        )

        try:
            cal = CalendarService()

            # Obtener evento actual y agregar marcador de completada
            service = cal.service
            event = service.events().get(
                calendarId=cal.calendar_id, eventId=event_id
            ).execute()

            current_desc = event.get("description", "")
            new_desc = f"{COMPLETED_MARKER} ✅\n{current_desc}".strip()

            cal.update_event(event_id, {"description": new_desc})

            # Preguntar si quiere eliminarla
            keyboard = [
                [
                    InlineKeyboardButton(
                        "🗑️ Eliminar del calendario",
                        callback_data=f"del_confirm_{event_id}",
                    ),
                    InlineKeyboardButton("📌 Mantener", callback_data="comp_cancelar"),
                ]
            ]

            await query.edit_message_text(
                f"✅ *{event_name}* marcada como completada!\n\n"
                "¿Quieres eliminarla del calendario o mantenerla?",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        except Exception as e:
            logger.error(f"Error completando tarea: {e}")
            await query.edit_message_text(f"❌ Error: {e}")


def get_completar_callback_handler() -> CallbackQueryHandler:
    """Devuelve el handler para callbacks de completar."""
    return CallbackQueryHandler(confirmar_completar, pattern=r"^comp_")
