import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from supplement_service import SupplementService
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

async def handle_suplemento_nlp(update: Update, context: ContextTypes.DEFAULT_TYPE, processing_msg, datos, respuesta):
    """Procesa el alta de un suplemento detectado por NLP."""
    suplementos = datos.get("suplementos")
    # Compatibilidad por si Gemini manda 'suplemento' como string
    if not suplementos:
        suplementos = [datos.get("suplemento")] if datos.get("suplemento") else []
    
    # Asegurar que es lista (si mandó un solo string en suplementos)
    if isinstance(suplementos, str):
        suplementos = [suplementos]
        
    hora = datos.get("hora_inicio")

    if not suplementos or not hora:
        await processing_msg.edit_text(
            respuesta or "Me falta el nombre del suplemento o la hora para agendarlo."
        )
        return

    try:
        # Validar formato de hora
        time_valid = datetime.strptime(hora, "%H:%M")
        
        service = SupplementService()
        added = []
        already_exist = []
        
        for sup in suplementos:
            success = service.add_supplement(sup, hora)
            if success:
                added.append(sup)
            else:
                already_exist.append(sup)
        
        msg_parts = []
        if added:
            msg_parts.append(f"✅ ¡Entendido! He anotado que tomas *{', '.join(added)}* todos los días a las *{hora}*.")
        if already_exist:
            msg_parts.append(f"ℹ️ *{', '.join(already_exist)}* ya estaban agendados a esa hora.")
            
        if added:
            msg_parts.append("\nTe avisaré por aquí a esa hora y no te dejaré tranquilo hasta que me confirmes 💊.")
        
        await processing_msg.edit_text("\n".join(msg_parts), parse_mode="Markdown")

    except ValueError:
        await processing_msg.edit_text("❌ La hora que entendí no tiene un formato válido (HH:MM).")
    except Exception as e:
        logger.error(f"Error registrando suplemento: {e}")
        await processing_msg.edit_text("❌ Hubo un error al guardar el recordatorio.")

async def supplement_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja los botones de Hecho / 30 min."""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split("|")
    action = data[0] # 'supp_done' o 'supp_snooze'
    names = data[1].split(",") # Lista de nombres de suplementos

    service = SupplementService()
    
    if action == "supp_done":
        today = datetime.now().strftime("%Y-%m-%d")
        service.mark_as_taken(names, today)
        await query.edit_message_text(
            f"✅ ¡Excelente! He marcado como tomados: *{', '.join(names)}*.\n¡Sigue así! 💪",
            parse_mode="Markdown"
        )
    
    elif action == "supp_snooze":
        next_time = datetime.now() + timedelta(minutes=30)
        service.set_next_reminder(names, next_time.isoformat())
        await query.edit_message_text(
            f"⏳ Entendido. Te volveré a preguntar por *{', '.join(names)}* en 30 minutos. ¡No se te olvide! 💊",
            parse_mode="Markdown"
        )

def get_supplement_callback_handler() -> CallbackQueryHandler:
    return CallbackQueryHandler(supplement_callback, pattern=r"^supp_")
