"""Sistema de recordatorios periódicos.

- Lee la agenda cada 2 horas (6:30 a 00:00)
- Envía recordatorios de reuniones/tareas pendientes
- Renueva tareas no completadas al día siguiente
"""

import logging
from datetime import datetime, timedelta, time

import pytz
from telegram.ext import ContextTypes

import config
from calendar_service import CalendarService, format_event

logger = logging.getLogger(__name__)
TZ = pytz.timezone(config.TIMEZONE)

COMPLETED_MARKER = "[COMPLETADA]"
# Prefijo para marcar tareas originales que ya fueron movidas/renovadas
RENEWED_MARKER = "[RENOVADA]"


async def check_agenda_and_remind(context: ContextTypes.DEFAULT_TYPE):
    """Job periódico: lee la agenda y envía recordatorios.

    Se ejecuta cada 2 horas entre 6:30 y 00:00.
    """
    now = datetime.now(TZ)
    current_hour = now.hour
    current_minute = now.minute

    # Solo ejecutar entre 6:30 y 00:00
    if current_hour < 6 or (current_hour == 6 and current_minute < 30):
        logger.info("Fuera de horario de recordatorios, ignorando.")
        return

    chat_id = config.AUTHORIZED_USER_ID
    if not chat_id:
        logger.warning("AUTHORIZED_USER_ID no configurado, no se envían recordatorios.")
        return

    logger.info(f"⏰ Ejecutando check de agenda - {now.strftime('%H:%M')}")

    try:
        cal = CalendarService()

        # === 1. Recordatorio de eventos de HOY pendientes ===
        today_events = cal.get_today_events()
        pending_events = []

        for event in today_events:
            # Ignorar eventos ya completados
            desc = event.get("description", "")
            if COMPLETED_MARKER in desc:
                continue

            start = event.get("start", {})

            if "date" in start and "dateTime" not in start:
                # Evento de día completo (tarea) → siempre mostrar
                pending_events.append(event)
            elif "dateTime" in start:
                event_dt = datetime.fromisoformat(start["dateTime"]).astimezone(TZ)
                if event_dt < now - timedelta(hours=1):
                    # Ya pasó hace más de 1 hora → solo mostrar si parece tarea
                    # (no tiene hora de fin definida o dura todo el día)
                    end = event.get("end", {})
                    if "dateTime" in end:
                        end_dt = datetime.fromisoformat(end["dateTime"]).astimezone(TZ)
                        duration = (end_dt - event_dt).total_seconds() / 3600
                        if duration >= 12:
                            # Parece tarea (dura 12+ horas), seguir mostrando
                            pending_events.append(event)
                        # Si no, ya pasó → no mostrar
                    else:
                        pending_events.append(event)
                else:
                    pending_events.append(event)

        if pending_events:
            lines = [f"⏰ *Recordatorio de agenda* ({now.strftime('%H:%M')})\n"]
            lines.append(f"📋 Tienes *{len(pending_events)}* evento(s) pendiente(s) hoy:\n")

            for event in pending_events:
                lines.append(format_event(event))

            lines.append("\n💡 _Escribe \"completé [nombre]\" para marcar como terminada._")

            await context.bot.send_message(
                chat_id=int(chat_id),
                text="\n\n".join(lines),
                parse_mode="Markdown",
            )
        else:
            # Siempre informar el estado
            if current_hour == 6:
                await context.bot.send_message(
                    chat_id=int(chat_id),
                    text="☀️ *Buenos días!*\n\nNo tienes eventos pendientes para hoy. 🎉",
                    parse_mode="Markdown",
                )
            else:
                await context.bot.send_message(
                    chat_id=int(chat_id),
                    text=f"✅ *Check {now.strftime('%H:%M')}* — No tienes tareas pendientes. ¡Todo al día! 🎉",
                    parse_mode="Markdown",
                )

        # === 2. Próximos eventos (dentro de las próximas 2 horas) ===
        upcoming_2h = []
        for event in today_events:
            start = event.get("start", {})
            if "dateTime" in start:
                event_dt = datetime.fromisoformat(start["dateTime"]).astimezone(TZ)
                diff = (event_dt - now).total_seconds() / 60
                if 0 < diff <= 120:  # Dentro de las próximas 2 horas
                    desc = event.get("description", "")
                    if COMPLETED_MARKER not in desc:
                        upcoming_2h.append((event, int(diff)))

        if upcoming_2h:
            lines = ["🔔 *Próximamente:*\n"]
            for event, mins in upcoming_2h:
                summary = event.get("summary", "Sin título")
                if mins < 60:
                    time_str = f"en {mins} minutos"
                else:
                    hours = mins // 60
                    remaining = mins % 60
                    time_str = f"en {hours}h {remaining}min"
                lines.append(f"• *{summary}* — {time_str}")

            await context.bot.send_message(
                chat_id=int(chat_id),
                text="\n".join(lines),
                parse_mode="Markdown",
            )

    except Exception as e:
        logger.error(f"Error en check de agenda: {e}")


async def send_morning_briefing(context: ContextTypes.DEFAULT_TYPE):
    """Job matutino (7:30 AM): envía el resumen del día."""
    chat_id = config.AUTHORIZED_USER_ID
    if not chat_id: return

    logger.info("☀️ Enviando briefing matutino...")
    try:
        cal = CalendarService()
        today_events = cal.get_today_events()
        
        if not today_events:
            await context.bot.send_message(
                chat_id=int(chat_id),
                text="☀️ *¡Buenos días!*\n\nHoy no tienes eventos agendados. ¡Disfruta tu día libre! 🎉",
                parse_mode="Markdown",
            )
            return

        lines = ["☀️ *Buenos días! Tu resumen para hoy:*\n"]
        for event in today_events:
            lines.append(format_event(event, show_past_marker=False))
        
        await context.bot.send_message(
            chat_id=int(chat_id),
            text="\n\n".join(lines),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Error en briefing matutino: {e}")


async def send_smart_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Job frecuente (cada 15 min): envía alertas push 15-30 min antes de eventos."""
    chat_id = config.AUTHORIZED_USER_ID
    if not chat_id: return

    now = datetime.now(TZ)
    try:
        cal = CalendarService()
        today_events = cal.get_today_events()
        
        for event in today_events:
            desc = event.get("description", "")
            if COMPLETED_MARKER in desc: continue
            
            start = event.get("start", {})
            if "dateTime" in start:
                event_dt = datetime.fromisoformat(start["dateTime"]).astimezone(TZ)
                diff = (event_dt - now).total_seconds() / 60
                
                # Alerta si faltan entre 14 y 16 minutos (para el trigger de 15 min)
                if 14 <= diff <= 16:
                    summary = event.get("summary", "Sin título")
                    await context.bot.send_message(
                        chat_id=int(chat_id),
                        text=f"🔔 *¡Atención!* Tu evento *{summary}* comienza en 15 minutos.",
                        parse_mode="Markdown",
                    )
    except Exception as e:
        logger.error(f"Error en smart reminders: {e}")


async def send_weekly_report(context: ContextTypes.DEFAULT_TYPE):
    """Job semanal (Domingo 9 PM): reporte de productividad."""
    chat_id = config.AUTHORIZED_USER_ID
    if not chat_id: return

    logger.info("📊 Generando reporte semanal...")
    try:
        cal = CalendarService()
        # Obtener eventos de los últimos 7 días
        now = datetime.now(TZ)
        start_week = now - timedelta(days=7)
        events = cal.list_events(start_week, now)
        
        total = len(events)
        completed = sum(1 for e in events if COMPLETED_MARKER in e.get("description", ""))
        
        if total == 0: return

        pct = (completed / total) * 100
        msg = (
            f"📊 *Reporte Semanal de Productividad*\n\n"
            f"✅ Tareas completadas: {completed}\n"
            f"📅 Total eventos: {total}\n"
            f"📈 Efectividad: {pct:.1f}%\n\n"
            f"{'¡Excelente trabajo esta semana! 🔥' if pct > 80 else '¡Buena semana! Vamos por más el lunes. 💪'}"
        )
        
        await context.bot.send_message(
            chat_id=int(chat_id),
            text=msg,
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Error en reporte semanal: {e}")


async def check_supplements_and_remind(context: ContextTypes.DEFAULT_TYPE):
    """Job frecuente (cada minuto): verifica si hay suplementos por tomar."""
    chat_id = config.AUTHORIZED_USER_ID
    if not chat_id: return

    now = datetime.now(TZ)
    current_time = now.strftime("%H:%M")
    current_date = now.strftime("%Y-%m-%d")

    try:
        from supplement_service import SupplementService
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        service = SupplementService()
        pending = service.get_pending(current_time, current_date)

        if not pending:
            return

        # Agrupar suplementos por mensaje (en este bot solo hay un usuario, así que todos juntos)
        names = [s["name"] for s in pending]
        names_str = ", ".join(names)
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Hecho", callback_data=f"supp_done|{','.join(names)}"),
                InlineKeyboardButton("⏳ en 30 min", callback_data=f"supp_snooze|{','.join(names)}"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(
            chat_id=int(chat_id),
            text=f"💊 *¡Hora de tu suplementación!* ({now.strftime('%H:%M')})\n\n"
                 f"Debes tomar:\n• *{names_str}* \n\n"
                 f"¿Ya lo hiciste?",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        
        # Para evitar enviar el mismo mensaje cada minuto de esa hora, 
        # marcamos el 'next_reminder' como +1 minuto temporalmente si es la hora exacta,
        # o simplemente confiamos en que 'get_pending' filtre los que ya enviamos reintento.
        # Mejor: si es la hora exacta, ponemos un reintento en 30 min por defecto para que no se repita.
        service.set_next_reminder(names, (now + timedelta(minutes=30)).isoformat())

    except Exception as e:
        logger.error(f"Error en check de suplementos: {e}")


async def renew_uncompleted_tasks(context: ContextTypes.DEFAULT_TYPE, target_date=None):
    """Job nocturno: renueva tareas no completadas para el día siguiente.
    
    Args:
        target_date: Fecha de la cual buscar pendientes (default: hoy).
    """
    chat_id = config.AUTHORIZED_USER_ID
    if not chat_id:
        return

    now = datetime.now(TZ)
    if not target_date:
        target_date = now.date()
    
    logger.info(f"🔄 Ejecutando renovación de tareas no completadas para la fecha {target_date}...")

    try:
        cal = CalendarService()
        # Obtener eventos de la fecha objetivo
        start_of_day = TZ.localize(datetime.combine(target_date, time.min))
        end_of_day = TZ.localize(datetime.combine(target_date, time.max))
        today_events = cal.list_events(start_of_day, end_of_day)
        
        renewed = []

        for event in today_events:
            desc = event.get("description", "")

            # Saltar eventos ya completados o que ya fueron renovados anteriormente
            if COMPLETED_MARKER in desc or RENEWED_MARKER in desc:
                continue

            summary = event.get("summary", "")
            start = event.get("start", {})
            end = event.get("end", {})

            # Calcular fecha de mañana (respecto a la fecha del evento)
            next_day = target_date + timedelta(days=1)
            next_day_start = TZ.localize(datetime.combine(next_day, datetime.min.time()))

            # === NUEVO: Evitar duplicados para eventos que ya cubren el día siguiente ===
            if "dateTime" in end:
                end_dt = datetime.fromisoformat(end["dateTime"]).astimezone(TZ)
                if end_dt > next_day_start:
                    continue
            elif "date" in end:
                end_d = datetime.strptime(end["date"], "%Y-%m-%d").date()
                if end_d > next_day:
                    continue

            if "dateTime" in start:
                # REUNIÓN: Ya no las renovamos por petición del usuario
                continue

            elif "date" in start:
                # TAREA de día completo: mover a mañana
                new_start = TZ.localize(
                    datetime.combine(next_day, datetime.min.time())
                )
                new_end = new_start + timedelta(days=1)
                new_desc = desc + "\n[Renovada - no completada el " + target_date.strftime("%d/%m/%Y") + "]"
                cal.create_event(
                    summary=f"📌 {summary}",
                    start_dt=new_start,
                    end_dt=new_end,
                    description=new_desc.strip(),
                    all_day=True,
                )
                
                # Marcar el evento original como ya renovado para evitar duplicados en reinicios
                original_desc = (desc + "\n" + RENEWED_MARKER).strip()
                cal.update_event(event["id"], {"description": original_desc})
                
                renewed.append(summary)

        if renewed:
            lines = ["🔄 *Tareas renovadas para mañana:*\n"]
            for name in renewed:
                lines.append(f"• 📌 {name}")
            lines.append("\n_No fueron completadas hoy, así que las moví a mañana._")

            await context.bot.send_message(
                chat_id=int(chat_id),
                text="\n".join(lines),
                parse_mode="Markdown",
            )
        else:
            await context.bot.send_message(
                chat_id=int(chat_id),
                text="✅ *Todas las tareas de hoy fueron completadas.* ¡Buen trabajo! 🎉",
                parse_mode="Markdown",
            )

    except Exception as e:
        logger.error(f"Error renovando tareas: {e}")


def setup_reminders(app):
    """Configura los jobs periódicos de recordatorios."""
    job_queue = app.job_queue

    # 1. Briefing matutino a las 7:30 AM
    job_queue.run_daily(send_morning_briefing, time=time(7, 30), name="morning_briefing")

    # 2. Smart Reminders (check cada 15 min)
    job_queue.run_repeating(send_smart_reminders, interval=900, first=60, name="smart_reminders")

    # 3. Reporte Semanal (Domingos 9 PM)
    # 0 = Lunes, 6 = Domingo
    job_queue.run_daily(send_weekly_report, time=time(21, 0), days=(6,), name="weekly_report")

    # 4. Check de Suplementos (cada minuto)
    job_queue.run_repeating(check_supplements_and_remind, interval=60, first=10, name="supplements")

    # 5. Check de agenda cada 2 horas (versión original mejorada)
    reminder_times = [
        time(6, 30), time(8, 30), time(10, 30), time(12, 30),
        time(14, 30), time(16, 30), time(18, 30), time(20, 30),
        time(22, 30), time(0, 0),
    ]

    for t in reminder_times:
        job_queue.run_daily(
            check_agenda_and_remind,
            time=t,
            name=f"reminder_{t.strftime('%H%M')}",
        )

    # 5. Renovación de tareas a las 23:59
    job_queue.run_daily(
        renew_uncompleted_tasks,
        time=time(23, 59),
        name="renew_tasks",
    )

    # === Catchups al inicio ===
    now = datetime.now(TZ)
    current_minutes = now.hour * 60 + now.minute

    # Si arrancamos después de las 7:30 pero antes de las 10:00, enviar briefing si no se envió
    if 450 <= current_minutes <= 600:
        job_queue.run_once(send_morning_briefing, when=15, name="briefing_catchup")

    # Catchup de renovación (mismo código existente)
    if (23 * 60 + 59) <= current_minutes <= (24 * 60):
        job_queue.run_once(renew_uncompleted_tasks, when=20)
    elif current_minutes <= (4 * 60):
        yesterday = now.date() - timedelta(days=1)
        job_queue.run_once(
            lambda context: renew_uncompleted_tasks(context, target_date=yesterday),
            when=30,
            name="renew_tasks_yesterday_catchup"
        )

