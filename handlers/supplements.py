import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from supplement_service import SupplementService
from datetime import datetime, timedelta
import pytz
import config

logger = logging.getLogger(__name__)

async def handle_suplemento_nlp(update: Update, context: ContextTypes.DEFAULT_TYPE, processing_msg, datos, respuesta, intencion_original=None):
    """Procesa el alta de un suplemento detectado por NLP."""
    
    # Si la intención es consultar o no hay datos suficientes, listamos los suplementos
    suplementos = datos.get("suplementos")
    hora = datos.get("hora_inicio")
    
    es_consulta = False
    if intencion_original == "suplementacion":
        # Si no hay suplementos ni hora, o si explícitamente se pide consultar (aunque el prompt actual pone datos vacíos)
        if not suplementos and not hora:
            es_consulta = True
            
    if es_consulta:
        service = SupplementService()
        all_supplements = service.get_all()
        
        if not all_supplements:
            msg = f"{respuesta}\n\n🚫 *No tienes ningún suplemento registrado aún.*" if respuesta else "🚫 *No tienes ningún suplemento registrado aún.*"
            await processing_msg.edit_text(msg, parse_mode="Markdown")
            return

        lines = [f"{respuesta or '💊 Tus suplementos registrados:'}\n"]
        
        # Agrupar por hora
        by_time = {}
        for s in all_supplements:
            if not s.get("active", True): continue
            t = s["time"]
            if t not in by_time: by_time[t] = []
            by_time[t].append(s["name"])
            
        for t in sorted(by_time.keys()):
            names = ", ".join(by_time[t])
            lines.append(f"• *{t}*: {names}")
            
        await processing_msg.edit_text("\n".join(lines), parse_mode="Markdown")
        return

    # --- Lógica de creación (existente) ---
    suplementos = datos.get("suplementos")
    # Compatibilidad por si Gemini manda 'suplemento' como string
    if not suplementos:
        suplementos = [datos.get("suplemento")] if datos.get("suplemento") else []
    
    # Asegurar que es lista
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
        datetime.strptime(hora, "%H:%M")
        
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
    action = data[0] # 'supp_done', 'supp_snooze', 'supp_t_done' o 'supp_t_snooze'
    payload = data[1] # Lista de nombres (old) o HH:MM (new)

    service = SupplementService()
    today = datetime.now().strftime("%Y-%m-%d")
    tz = pytz.timezone(config.TIMEZONE)
    
    # NUEVOS: Basados en tiempo (agrupados)
    if action == "supp_t_done":
        service.mark_as_taken_by_time(payload, today)
        await query.edit_message_text(
            f"✅ ¡Excelente! He marcado como tomados los suplementos de las *{payload}*.\n¡Sigue así! 💪",
            parse_mode="Markdown"
        )
    elif action == "supp_t_snooze":
        next_time = datetime.now(tz) + timedelta(minutes=30)
        service.set_next_reminder_by_time(payload, next_time.isoformat())
        await query.edit_message_text(
            f"⏳ Entendido. Te volveré a preguntar por los suplementos de las *{payload}* en 30 minutos. ¡No se te olvide! 💊",
            parse_mode="Markdown"
        )
    
    # ANTERIORES: Basados en nombres (para compatibilidad)
    elif action == "supp_done":
        names = payload.split(",")
        service.mark_as_taken(names, today)
        await query.edit_message_text(
            f"✅ ¡Excelente! He marcado como tomados: *{', '.join(names)}*.\n¡Sigue así! 💪",
            parse_mode="Markdown"
        )
    elif action == "supp_snooze":
        names = payload.split(",")
        next_time = datetime.now(tz) + timedelta(minutes=30)
        service.set_next_reminder(names, next_time.isoformat())
        await query.edit_message_text(
            f"⏳ Entendido. Te volveré a preguntar por *{', '.join(names)}* en 30 minutos. ¡No se te olvide! 💊",
            parse_mode="Markdown"
        )


async def debug_suplementos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando de depuración para ver el estado interno de los suplementos."""
    service = SupplementService()
    all_s = service.get_all()
    
    if not all_s:
        await update.message.reply_text("No hay suplementos registrados.")
        return
        
    lines = ["🧪 *Estado de Suplementos (Debug):*"]
    tz = pytz.timezone(config.TIMEZONE)
    now = datetime.now(tz)
    
    for s in all_s:
        status = "✅" if s.get("active", True) else "❌"
        line = [
            f"{status} *{s['name']}*",
            f"  - ID: `{s.get('id', 'N/A')}`",
            f"  - Hora: `{s['time']}`",
            f"  - Última vez: `{s.get('last_taken_date', 'Nunca')}`"
        ]
        
        next_rem = s.get("next_reminder")
        if next_rem:
            try:
                nr_dt = datetime.fromisoformat(next_rem)
                if nr_dt.tzinfo is None:
                    nr_dt = tz.localize(nr_dt)
                
                diff = nr_dt - now
                diff_sec = int(diff.total_seconds())
                if diff_sec > 0:
                    line.append(f"  - Reintento en: `{diff_sec // 60}m {diff_sec % 60}s`")
                else:
                    line.append(f"  - Reintento: `VENCIDO` (hace {-diff_sec // 60}m)")
            except:
                line.append(f"  - Reintento: `{next_rem}`")
        else:
              line.append("  - Reintento: `Ninguno` (esperando hora exacta)")
              
        lines.append("\n".join(line))
        
    await update.message.reply_text("\n\n".join(lines), parse_mode="Markdown")


def get_supplement_callback_handler() -> CallbackQueryHandler:
    return CallbackQueryHandler(supplement_callback, pattern=r"^supp_")
