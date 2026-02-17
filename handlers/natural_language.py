"""Handler para mensajes de texto libre — procesamiento con NLP."""

import logging
from datetime import datetime

import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler

import config
from calendar_service import CalendarService, format_event
from nlp_processor import parse_user_message

logger = logging.getLogger(__name__)
TZ = pytz.timezone(config.TIMEZONE)


async def handle_natural_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa mensajes de texto libre usando Gemini NLP."""
    text = update.message.text

    # Mostrar que estamos procesando
    processing_msg = await update.message.reply_text("🤔 Procesando tu mensaje...")

    try:
        result = parse_user_message(text)
    except Exception as e:
        logger.error(f"Error en NLP: {e}")
        await processing_msg.edit_text("❌ Error procesando el mensaje. Intenta de nuevo.")
        return

    intencion = result.get("intencion", "otro")
    datos = result.get("datos", {})
    respuesta = result.get("respuesta", "")

    if intencion == "crear":
        await _handle_crear(update, context, processing_msg, datos, respuesta)
    elif intencion == "listar":
        await _handle_listar(update, context, processing_msg, datos, respuesta)
    elif intencion == "eliminar":
        await _handle_eliminar(update, context, processing_msg, datos, respuesta)
    elif intencion == "completar":
        await _handle_completar(update, context, processing_msg, datos, respuesta)
    elif intencion == "consultar":
        await _handle_consultar(update, context, processing_msg, datos, respuesta)
    else:
        await processing_msg.edit_text(
            respuesta or "No entendí bien. Prueba con algo como:\n"
            '• _"Reunión mañana a las 3pm"_\n'
            '• _"¿Qué tengo hoy?"_\n'
            '• _"Elimina la reunión del viernes"_',
            parse_mode="Markdown",
        )


async def _handle_crear(update, context, processing_msg, datos, respuesta):
    """Crea un evento a partir de datos extraídos por NLP."""
    titulo = datos.get("titulo", "")
    tipo = datos.get("tipo", "reunion")
    fecha_str = datos.get("fecha")
    hora_inicio = datos.get("hora_inicio")
    hora_fin = datos.get("hora_fin")
    descripcion = datos.get("descripcion", "")
    dia_completo = datos.get("dia_completo", False)

    # Las tareas SIEMPRE son de día completo
    if tipo == "tarea":
        dia_completo = True
        hora_inicio = None
        hora_fin = None
        if not fecha_str:
            fecha_str = datetime.now(TZ).strftime("%Y-%m-%d")

    if not titulo:
        await processing_msg.edit_text(
            f"{respuesta}\n\n❓ No pude identificar el título del evento. "
            "¿Puedes ser más específico?"
        )
        return

    if not fecha_str:
        await processing_msg.edit_text(
            f"{respuesta}\n\n❓ No pude identificar la fecha. "
            "¿Puedes incluir cuándo sería?"
        )
        return

    try:
        fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        await processing_msg.edit_text(
            f"{respuesta}\n\n❓ No pude interpretar la fecha correctamente."
        )
        return

    if dia_completo or not hora_inicio:
        start_dt = TZ.localize(datetime.combine(fecha, datetime.min.time()))
        all_day = True
        hora_display = "Todo el día"
    else:
        try:
            hora = datetime.strptime(hora_inicio, "%H:%M").time()
            start_dt = TZ.localize(datetime.combine(fecha, hora))
            all_day = False
            hora_display = hora_inicio
        except (ValueError, TypeError):
            start_dt = TZ.localize(datetime.combine(fecha, datetime.min.time()))
            all_day = True
            hora_display = "Todo el día"

    end_dt = None
    if hora_fin and not all_day:
        try:
            hora_f = datetime.strptime(hora_fin, "%H:%M").time()
            end_dt = TZ.localize(datetime.combine(fecha, hora_f))
        except (ValueError, TypeError):
            pass

    # Guardar datos en contexto para confirmación
    context.user_data["nlp_evento"] = {
        "titulo": titulo,
        "start_dt": start_dt,
        "end_dt": end_dt,
        "descripcion": descripcion,
        "all_day": all_day,
    }

    keyboard = [
        [
            InlineKeyboardButton("✅ Crear", callback_data="nlp_crear_si"),
            InlineKeyboardButton("❌ Cancelar", callback_data="nlp_crear_no"),
        ]
    ]

    tipo_label = "📝 Tarea" if tipo == "tarea" else "📅 Reunión"
    await processing_msg.edit_text(
        f"{respuesta}\n\n"
        f"📋 *Resumen ({tipo_label}):*\n"
        f"📌 *{titulo}*\n"
        f"📅 {fecha.strftime('%d/%m/%Y')}\n"
        f"🕐 {hora_display}\n"
        f"{'📝 ' + descripcion if descripcion else ''}\n\n"
        "¿Confirmo la creación?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def confirmar_nlp_crear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback para confirmar/cancelar creación por NLP."""
    query = update.callback_query
    await query.answer()

    if query.data == "nlp_crear_no":
        await query.edit_message_text("❌ Evento cancelado.")
        context.user_data.pop("nlp_evento", None)
        return

    evento_data = context.user_data.pop("nlp_evento", None)
    if not evento_data:
        await query.edit_message_text("❌ No hay evento pendiente para crear.")
        return

    try:
        cal = CalendarService()
        event = cal.create_event(
            summary=evento_data["titulo"],
            start_dt=evento_data["start_dt"],
            end_dt=evento_data["end_dt"],
            description=evento_data.get("descripcion", ""),
            all_day=evento_data["all_day"],
        )

        link = event.get("htmlLink", "")
        await query.edit_message_text(
            f"✅ *Evento creado!*\n\n"
            f"📌 {evento_data['titulo']}\n"
            f"🔗 [Ver en Google Calendar]({link})",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Error creando evento NLP: {e}")
        await query.edit_message_text(f"❌ Error al crear: {e}")


async def _handle_listar(update, context, processing_msg, datos, respuesta):
    """Lista eventos: tareas pendientes + eventos futuros, con soporte para fecha específica."""
    try:
        cal = CalendarService()
        rango = datos.get("rango_dias", 7)
        fecha_especifica_str = datos.get("fecha")
        
        now = datetime.now(TZ)
        from reminder_scheduler import COMPLETED_MARKER

        if fecha_especifica_str:
            # Caso A: El usuario pidió una fecha específica (ej: "qué tengo mañana")
            try:
                fecha_req = datetime.strptime(fecha_especifica_str, "%Y-%m-%d").date()
                start_req = TZ.localize(datetime.combine(fecha_req, datetime.min.time()))
                end_req = TZ.localize(datetime.combine(fecha_req, datetime.max.time()))
                
                events = cal.list_events(start_req, end_req)
                
                # Filtrar: no mostrar pasados con hora, mantener tareas todo el día
                filtered = []
                for e in events:
                    if COMPLETED_MARKER in e.get("description", ""):
                        continue
                    
                    start = e.get("start", {})
                    if "date" in start and "dateTime" not in start:
                        filtered.append(e)
                    elif "dateTime" in start:
                        dt_start = datetime.fromisoformat(start["dateTime"]).astimezone(TZ)
                        end = e.get("end", {})
                        if "dateTime" in end:
                            dt_end = datetime.fromisoformat(end["dateTime"]).astimezone(TZ)
                            # Incluir si: no ha empezado O si ya empezó pero no ha terminado
                            if dt_start > now or dt_end > now:
                                filtered.append(e)
                        elif dt_start > now:
                            filtered.append(e)
                
                if not filtered:
                    await processing_msg.edit_text(
                        f"{respuesta}\n\n📭 No tienes eventos pendientes para esa fecha."
                    )
                    return

                lines = [f"{respuesta}\n"]
                lines.append(f"📅 *Agenda para el {fecha_req.strftime('%d/%m/%Y')}*:\n")
                for e in filtered:
                    lines.append(format_event(e, show_past_marker=False))
                
                await processing_msg.edit_text("\n\n".join(lines), parse_mode="Markdown")
                
            except ValueError:
                await processing_msg.edit_text("❌ No pude interpretar la fecha correctamente.")
                return

        else:
            # Caso B: Listado general (Próximos 7 días)
            # 1. Tareas de HOY que no fueron completadas (aunque la hora pasó, si son tareas)
            today_events = cal.get_today_events()
            pending_today = []

            for e in today_events:
                if COMPLETED_MARKER in e.get("description", ""):
                    continue
                
                start = e.get("start", {})
                if "date" in start and "dateTime" not in start:
                    pending_today.append(e)
                elif "dateTime" in start:
                    dt_start = datetime.fromisoformat(start["dateTime"]).astimezone(TZ)
                    end = e.get("end", {})
                    if "dateTime" in end:
                        dt_end = datetime.fromisoformat(end["dateTime"]).astimezone(TZ)
                        if dt_start > now or dt_end > now:
                            pending_today.append(e)
                    elif dt_start > now:
                        pending_today.append(e)

            # 2. Eventos futuros (desde mañana hasta el rango solicitado)
            from datetime import timedelta, time as dt_time
            tomorrow_start = TZ.localize(datetime.combine(
                now.date() + timedelta(days=1), dt_time.min
            ))
            end_range = tomorrow_start + timedelta(days=rango - 1)
            future_events = cal.list_events(tomorrow_start, end_range) if rango > 1 else []

            all_events = pending_today + future_events

            if not all_events:
                await processing_msg.edit_text(
                    f"{respuesta}\n\n📭 No encontré eventos pendientes."
                )
                return

            lines = [f"{respuesta}\n"]
            if pending_today:
                lines.append(f"📋 *Pendientes de hoy* ({len(pending_today)}):\n")
                for event in pending_today:
                    lines.append(format_event(event, show_past_marker=False))
                lines.append("")

            if future_events:
                lines.append(f"📅 *Próximos días*:\n")
                for event in future_events:
                    lines.append(format_event(event, show_past_marker=False))

            await processing_msg.edit_text("\n\n".join(lines), parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Error listando eventos NLP: {e}")
        await processing_msg.edit_text(f"❌ Error: {e}")


async def _handle_eliminar(update, context, processing_msg, datos, respuesta):
    """Busca y ofrece eliminar un evento por nombre."""
    titulo_buscar = datos.get("titulo", "")

    try:
        cal = CalendarService()
        events = cal.get_upcoming_events(days=30)

        if not events:
            await processing_msg.edit_text(
                f"{respuesta}\n\n📭 No hay eventos para eliminar."
            )
            return

        # Buscar coincidencias por nombre
        if titulo_buscar:
            matches = [
                e for e in events
                if titulo_buscar.lower() in e.get("summary", "").lower()
            ]
        else:
            matches = events[:10]

        if not matches:
            await processing_msg.edit_text(
                f"{respuesta}\n\n❓ No encontré eventos que coincidan con *{titulo_buscar}*.",
                parse_mode="Markdown",
            )
            return

        context.user_data["eventos_para_eliminar"] = {
            e["id"]: e.get("summary", "Sin título") for e in matches
        }

        keyboard = []
        for event in matches[:10]:
            summary = event.get("summary", "Sin título")
            label = f"🗑️ {summary}"
            if len(label) > 60:
                label = label[:57] + "..."
            keyboard.append([
                InlineKeyboardButton(label, callback_data=f"del_{event['id']}")
            ])
        keyboard.append([
            InlineKeyboardButton("❌ Cancelar", callback_data="del_cancelar")
        ])

        await processing_msg.edit_text(
            f"{respuesta}\n\n🗑️ *¿Cuál quieres eliminar?*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    except Exception as e:
        logger.error(f"Error buscando eventos para eliminar: {e}")
        await processing_msg.edit_text(f"❌ Error: {e}")


async def _handle_completar(update, context, processing_msg, datos, respuesta):
    """Marca una tarea como completada buscándola por nombre."""
    from reminder_scheduler import COMPLETED_MARKER
    titulo_buscar = datos.get("titulo", "")

    try:
        cal = CalendarService()
        today_events = cal.get_today_events()

        # Buscar pendientes (no completadas)
        pending = [
            e for e in today_events
            if COMPLETED_MARKER not in e.get("description", "")
        ]

        if not pending:
            await processing_msg.edit_text(
                f"{respuesta}\n\n✅ No tienes tareas pendientes hoy."
            )
            return

        # Buscar coincidencia por nombre
        if titulo_buscar:
            matches = [
                e for e in pending
                if titulo_buscar.lower() in e.get("summary", "").lower()
            ]
        else:
            matches = []

        if len(matches) == 1:
            # Match exacto: completar directamente
            event = matches[0]
            event_id = event["id"]
            summary = event.get("summary", "tarea")

            service = cal.service
            full_event = service.events().get(
                calendarId=cal.calendar_id, eventId=event_id
            ).execute()

            current_desc = full_event.get("description", "")
            new_desc = f"{COMPLETED_MARKER} ✅\n{current_desc}".strip()
            cal.update_event(event_id, {"description": new_desc})

            await processing_msg.edit_text(
                f"✅ *{summary}* marcada como completada! 🎉",
                parse_mode="Markdown",
            )
        elif len(matches) > 1:
            # Múltiples matches: ofrecer selección
            context.user_data["eventos_completar"] = {
                e["id"]: e.get("summary", "Sin título") for e in matches
            }
            keyboard = []
            for event in matches:
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
            await processing_msg.edit_text(
                f"{respuesta}\n\nEncontré varias coincidencias. ¿Cuál completaste?",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        else:
            # Sin coincidencias: mostrar todas las pendientes
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
            await processing_msg.edit_text(
                f"{respuesta}\n\nNo encontré una coincidencia exacta. "
                "¿Cuál completaste?",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
    except Exception as e:
        logger.error(f"Error completando tarea NLP: {e}")
        await processing_msg.edit_text(f"❌ Error: {e}")


async def _handle_consultar(update, context, processing_msg, datos, respuesta):
    """Responde consultas sobre la agenda."""
    try:
        cal = CalendarService()
        events = cal.get_upcoming_events(days=7)

        if events:
            lines = [f"{respuesta}\n"]
            for event in events[:5]:
                lines.append(format_event(event))
            await processing_msg.edit_text(
                "\n\n".join(lines),
                parse_mode="Markdown",
            )
        else:
            await processing_msg.edit_text(
                f"{respuesta}\n\n📭 No tienes eventos próximos."
            )
    except Exception as e:
        logger.error(f"Error consultando: {e}")
        await processing_msg.edit_text(f"❌ Error: {e}")


def get_nlp_callback_handler() -> CallbackQueryHandler:
    """Devuelve el handler para callbacks de NLP crear."""
    return CallbackQueryHandler(confirmar_nlp_crear, pattern=r"^nlp_crear_")
