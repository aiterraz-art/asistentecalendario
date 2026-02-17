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

# Prefijo para marcar tareas completadas en la descripción
COMPLETED_MARKER = "[COMPLETADA]"


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

            # Saltar eventos ya completados
            if COMPLETED_MARKER in desc:
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
    """Configura los jobs periódicos de recordatorios.

    Horarios:
    - Cada 2 horas de 6:30 a 00:00: check de agenda
    - 23:55: renovación de tareas no completadas
    """
    job_queue = app.job_queue

    # Check de agenda cada 2 horas empezando a las 6:30
    reminder_times = [
        time(6, 30),
        time(8, 30),
        time(10, 30),
        time(12, 30),
        time(14, 30),
        time(16, 30),
        time(18, 30),
        time(20, 30),
        time(22, 30),
        time(0, 0),   # Medianoche
    ]

    for t in reminder_times:
        job_queue.run_daily(
            check_agenda_and_remind,
            time=t,
            name=f"reminder_{t.strftime('%H%M')}",
        )
        logger.info(f"📅 Recordatorio programado a las {t.strftime('%H:%M')}")

    # Renovación de tareas a las 23:55
    job_queue.run_daily(
        renew_uncompleted_tasks,
        time=time(23, 55),
        name="renew_tasks",
    )
    logger.info("🔄 Renovación de tareas programada a las 23:55")

    # === Check al inicio: si se perdió un recordatorio reciente, enviar ahora ===
    now = datetime.now(TZ)
    current_minutes = now.hour * 60 + now.minute

    # Verificar si algún recordatorio debió haber sonado en los últimos 30 min
    for t in reminder_times:
        t_minutes = t.hour * 60 + t.minute
        diff = current_minutes - t_minutes
        if 0 < diff <= 30:
            # Se perdió un recordatorio reciente, enviar en 10 segundos
            logger.info(
                f"⚠️ Recordatorio de las {t.strftime('%H:%M')} perdido "
                f"(hace {diff} min). Enviando ahora..."
            )
            job_queue.run_once(
                check_agenda_and_remind,
                when=10,  # 10 segundos después del inicio
                name="reminder_startup_catchup",
            )
            break  # Solo enviar uno

    # Verificar si se perdió la renovación de tareas (23:55)
    # Si arrancamos entre 23:55 y 04:00 AM, ejecutar renovación para "ayer"
    if (23 * 60 + 55) <= current_minutes <= (24 * 60):
        # Caso: hoy antes de medianoche
        logger.info("⚠️ Se perdió la renovación de tareas de hoy. Ejecutando ahora...")
        job_queue.run_once(renew_uncompleted_tasks, when=20)
    elif current_minutes <= (4 * 60):
        # Caso: madrugada (00:00 - 04:00), renovar las de AYER
        yesterday = now.date() - timedelta(days=1)
        logger.info(f"⚠️ Bot iniciado en la madrugada. Renovando tareas pendientes de ayer ({yesterday})...")
        
        # Necesitamos pasar yesterday de alguna forma. APScheduler permite pasar args
        job_queue.run_once(
            lambda context: renew_uncompleted_tasks(context, target_date=yesterday),
            when=20,
            name="renew_tasks_yesterday_catchup"
        )

