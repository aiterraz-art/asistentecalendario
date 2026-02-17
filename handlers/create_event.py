"""Handler para crear eventos — flujo conversacional con /nuevo."""

import logging
from datetime import datetime, timedelta

import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

import config
from calendar_service import CalendarService, format_event

logger = logging.getLogger(__name__)
TZ = pytz.timezone(config.TIMEZONE)

# Estados de la conversación
TITULO, FECHA, HORA, CONFIRMAR = range(4)


async def nuevo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia el flujo de creación de evento paso a paso."""
    await update.message.reply_text(
        "📝 *Crear nuevo evento*\n\n"
        "¿Cuál es el título del evento?",
        parse_mode="Markdown",
    )
    return TITULO


async def recibir_titulo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el título y pide la fecha."""
    context.user_data["nuevo_titulo"] = update.message.text
    await update.message.reply_text(
        f'✅ Título: *{update.message.text}*\n\n'
        "📅 ¿Qué fecha? (formato: DD/MM/AAAA)\n"
        "O escribe _hoy_, _mañana_, _lunes_, etc.",
        parse_mode="Markdown",
    )
    return FECHA


async def recibir_fecha(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe la fecha y pide la hora."""
    text = update.message.text.strip().lower()
    now = datetime.now(TZ)

    # Interpretar fechas relativas
    if text == "hoy":
        fecha = now.date()
    elif text == "mañana":
        fecha = (now + timedelta(days=1)).date()
    else:
        # Intentar días de la semana
        dias = {
            "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2,
            "jueves": 3, "viernes": 4, "sábado": 5, "sabado": 5, "domingo": 6,
        }
        if text in dias:
            target_day = dias[text]
            days_ahead = target_day - now.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            fecha = (now + timedelta(days=days_ahead)).date()
        else:
            # Intentar formato DD/MM/AAAA
            try:
                fecha = datetime.strptime(text, "%d/%m/%Y").date()
            except ValueError:
                try:
                    fecha = datetime.strptime(text, "%d/%m").replace(year=now.year).date()
                except ValueError:
                    await update.message.reply_text(
                        "❌ No entendí la fecha. Prueba con:\n"
                        "• _hoy_, _mañana_, _lunes_, _martes_...\n"
                        "• _DD/MM/AAAA_ (ej: 20/02/2026)",
                        parse_mode="Markdown",
                    )
                    return FECHA

    context.user_data["nuevo_fecha"] = fecha
    await update.message.reply_text(
        f"✅ Fecha: *{fecha.strftime('%d/%m/%Y')}*\n\n"
        "🕐 ¿A qué hora? (formato: HH:MM, ej: 15:30)\n"
        "O escribe _todo el día_ si no tiene hora específica.",
        parse_mode="Markdown",
    )
    return HORA


async def recibir_hora(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe la hora y muestra resumen para confirmar."""
    text = update.message.text.strip().lower()
    fecha = context.user_data["nuevo_fecha"]
    titulo = context.user_data["nuevo_titulo"]

    if text in ("todo el día", "todo el dia", "dia completo", "día completo"):
        context.user_data["nuevo_all_day"] = True
        context.user_data["nuevo_start"] = TZ.localize(
            datetime.combine(fecha, datetime.min.time())
        )
        hora_str = "Todo el día"
    else:
        try:
            hora = datetime.strptime(text, "%H:%M").time()
        except ValueError:
            try:
                hora = datetime.strptime(text, "%H").time()
            except ValueError:
                await update.message.reply_text(
                    "❌ No entendí la hora. Prueba con formato HH:MM (ej: 15:30)"
                )
                return HORA

        context.user_data["nuevo_all_day"] = False
        start_dt = TZ.localize(datetime.combine(fecha, hora))
        context.user_data["nuevo_start"] = start_dt
        hora_str = hora.strftime("%H:%M")

    # Mostrar resumen
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirmar", callback_data="confirmar_si"),
            InlineKeyboardButton("❌ Cancelar", callback_data="confirmar_no"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "📋 *Resumen del evento:*\n\n"
        f"📌 *Título:* {titulo}\n"
        f"📅 *Fecha:* {fecha.strftime('%d/%m/%Y')}\n"
        f"🕐 *Hora:* {hora_str}\n\n"
        "¿Confirmar creación?",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )
    return CONFIRMAR


async def confirmar_evento(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Procesa la confirmación o cancelación del evento."""
    query = update.callback_query
    await query.answer()

    if query.data == "confirmar_no":
        await query.edit_message_text("❌ Evento cancelado.")
        context.user_data.clear()
        return ConversationHandler.END

    # Crear el evento
    titulo = context.user_data["nuevo_titulo"]
    start_dt = context.user_data["nuevo_start"]
    all_day = context.user_data["nuevo_all_day"]

    try:
        cal = CalendarService()
        event = cal.create_event(
            summary=titulo,
            start_dt=start_dt,
            all_day=all_day,
        )

        link = event.get("htmlLink", "")
        await query.edit_message_text(
            f"✅ *Evento creado exitosamente!*\n\n"
            f"📌 {titulo}\n"
            f"🔗 [Ver en Google Calendar]({link})",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Error creando evento: {e}")
        await query.edit_message_text(
            f"❌ Error al crear el evento: {e}"
        )

    context.user_data.clear()
    return ConversationHandler.END


async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela el flujo de creación."""
    await update.message.reply_text("❌ Creación de evento cancelada.")
    context.user_data.clear()
    return ConversationHandler.END


def get_create_event_handler() -> ConversationHandler:
    """Devuelve el ConversationHandler para crear eventos."""
    return ConversationHandler(
        entry_points=[CommandHandler("nuevo", nuevo_command)],
        states={
            TITULO: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_titulo)],
            FECHA: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_fecha)],
            HORA: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_hora)],
            CONFIRMAR: [CallbackQueryHandler(confirmar_evento)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
        allow_reentry=True,
    )
