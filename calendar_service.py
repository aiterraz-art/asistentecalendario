"""Wrapper para interactuar con Google Calendar API."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, time
from typing import Optional

import pytz

import config
from google_auth import get_calendar_service

logger = logging.getLogger(__name__)

# Zona horaria configurada
TZ = pytz.timezone(config.TIMEZONE)


class CalendarService:
    """Servicio para gestionar eventos en Google Calendar."""

    def __init__(self):
        self.service = get_calendar_service()
        self.calendar_id = "primary"

    def _refresh_service(self):
        """Refresca el servicio en caso de token expirado."""
        self.service = get_calendar_service()

    def list_events(
        self,
        time_min: datetime,
        time_max: datetime,
        max_results: int = 50,
    ) -> list[dict]:
        """Lista eventos entre dos fechas."""
        try:
            result = (
                self.service.events()
                .list(
                    calendarId=self.calendar_id,
                    timeMin=time_min.isoformat(),
                    timeMax=time_max.isoformat(),
                    maxResults=max_results,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            return result.get("items", [])
        except Exception as e:
            logger.error(f"Error listando eventos: {e}")
            self._refresh_service()
            raise

    def get_today_events(self) -> list[dict]:
        """Devuelve los eventos de hoy."""
        now = datetime.now(TZ)
        start_of_day = TZ.localize(datetime.combine(now.date(), time.min))
        end_of_day = TZ.localize(datetime.combine(now.date(), time.max))
        return self.list_events(start_of_day, end_of_day)

    def get_upcoming_events(self, days: int = 7) -> list[dict]:
        """Devuelve los eventos futuros de los próximos N días (desde ahora)."""
        now = datetime.now(TZ)
        end = now + timedelta(days=days)
        return self.list_events(now, end)

    def create_event(
        self,
        summary: str,
        start_dt: datetime,
        end_dt: Optional[datetime] = None,
        description: str = "",
        all_day: bool = False,
    ) -> dict:
        """Crea un evento en Google Calendar.

        Args:
            summary: Título del evento.
            start_dt: Fecha/hora de inicio (con timezone).
            end_dt: Fecha/hora de fin. Si es None, se pone 1 hora después.
            description: Descripción opcional.
            all_day: Si es True, crea un evento de día completo.
        """
        if not end_dt:
            end_dt = start_dt + timedelta(hours=1)

        if all_day:
            event_body = {
                "summary": summary,
                "description": description,
                "start": {"date": start_dt.strftime("%Y-%m-%d")},
                "end": {"date": end_dt.strftime("%Y-%m-%d")},
            }
        else:
            event_body = {
                "summary": summary,
                "description": description,
                "start": {
                    "dateTime": start_dt.isoformat(),
                    "timeZone": config.TIMEZONE,
                },
                "end": {
                    "dateTime": end_dt.isoformat(),
                    "timeZone": config.TIMEZONE,
                },
            }

        try:
            event = (
                self.service.events()
                .insert(calendarId=self.calendar_id, body=event_body)
                .execute()
            )
            logger.info(f"Evento creado: {event.get('htmlLink')}")
            return event
        except Exception as e:
            logger.error(f"Error creando evento: {e}")
            self._refresh_service()
            raise

    def delete_event(self, event_id: str) -> bool:
        """Elimina un evento por su ID."""
        try:
            self.service.events().delete(
                calendarId=self.calendar_id, eventId=event_id
            ).execute()
            logger.info(f"Evento eliminado: {event_id}")
            return True
        except Exception as e:
            logger.error(f"Error eliminando evento: {e}")
            self._refresh_service()
            raise

    def update_event(self, event_id: str, updates: dict) -> dict:
        """Actualiza campos de un evento existente."""
        try:
            event = (
                self.service.events()
                .get(calendarId=self.calendar_id, eventId=event_id)
                .execute()
            )
            event.update(updates)
            updated = (
                self.service.events()
                .update(
                    calendarId=self.calendar_id,
                    eventId=event_id,
                    body=event,
                )
                .execute()
            )
            logger.info(f"Evento actualizado: {event_id}")
            return updated
        except Exception as e:
            logger.error(f"Error actualizando evento: {e}")
            self._refresh_service()
            raise


def format_event(event: dict, show_past_marker: bool = True) -> str:
    """Formatea un evento para mostrarlo en Telegram."""
    summary = event.get("summary", "Sin título")
    now = datetime.now(TZ)
    is_past = False

    start = event.get("start", {})
    if "dateTime" in start:
        dt = datetime.fromisoformat(start["dateTime"])
        dt_local = dt.astimezone(TZ)
        date_str = dt_local.strftime("%d/%m/%Y")
        time_str = dt_local.strftime("%H:%M")
        is_past = dt_local < now
        when = f"📅 {date_str}  🕐 {time_str}"
    elif "date" in start:
        dt = datetime.strptime(start["date"], "%Y-%m-%d")
        is_past = dt.date() < now.date()
        when = f"📅 {dt.strftime('%d/%m/%Y')}  (todo el día)"
    else:
        when = "📅 Fecha no disponible"

    past_marker = " ✅ _pasado_" if (is_past and show_past_marker) else ""
    description = event.get("description", "")
    desc_line = f"\n📝 {description}" if description else ""

    return f"• *{summary}*{past_marker}\n  {when}{desc_line}"
