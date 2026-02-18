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

    def check_conflicts(self, start_dt: datetime, end_dt: datetime) -> list[dict]:
        """Busca eventos que se solapen con el rango dado."""
        try:
            events = self.list_events(start_dt, end_dt)
            # Filtrar eventos que no sean de todo el día para mayor precisión en conflictos de hora
            conflicts = []
            for e in events:
                start = e.get("start", {})
                if "dateTime" in start:
                    conflicts.append(e)
            return conflicts
        except Exception as e:
            logger.error(f"Error comprobando conflictos: {e}")
            return []

    def create_event(
        self,
        summary: str,
        start_dt: datetime,
        end_dt: Optional[datetime] = None,
        description: str = "",
        all_day: bool = False,
        location: str = "",
        metadata: Optional[dict] = None,
    ) -> dict:
        """Crea un evento en Google Calendar.

        Args:
            summary: Título del evento.
            start_dt: Fecha/hora de inicio (con timezone).
            end_dt: Fecha/hora de fin.
            description: Descripción opcional.
            all_day: Si es True, crea un evento de día completo.
            location: Ubicación física o nombre del lugar.
            metadata: Diccionario opcional con prioridad y categoría.
        """
        if not end_dt:
            end_dt = start_dt + timedelta(hours=1)

        # Mapeo de Prioridades a Emojis y Colores de Google Calendar
        # Colores Google: 11 (Rojo), 5 (Amarillo), 2 (Verde)
        prio_map = {
            "alta": {"emoji": "🔴", "color": "11"},
            "media": {"emoji": "🟡", "color": "5"},
            "baja": {"emoji": "🟢", "color": "2"},
        }
        
        current_prio = "media"
        enriched_summary = summary
        color_id = "5"

        if metadata:
            current_prio = metadata.get("prioridad", "media").lower()
            prio_data = prio_map.get(current_prio, prio_map["media"])
            enriched_summary = f"{prio_data['emoji']} {summary}"
            color_id = prio_data["color"]

        # Enriquecer descripción con metadatos si existen
        enriched_desc = description
        if metadata:
            cat = metadata.get("categoria", "personal").upper()
            meta_line = f"--- METADATA ---\nPRIORIDAD: {current_prio.upper()}\nCATEGORIA: {cat}\n"
            enriched_desc = f"{meta_line}\n{description}".strip()

        if all_day:
            if not end_dt or end_dt.date() <= start_dt.date():
                end_date_str = (start_dt + timedelta(days=1)).strftime("%Y-%m-%d")
            else:
                end_date_str = end_dt.strftime("%Y-%m-%d")

            event_body = {
                "summary": enriched_summary,
                "description": enriched_desc,
                "location": location,
                "visibility": "public",
                "colorId": color_id,
                "start": {"date": start_dt.strftime("%Y-%m-%d")},
                "end": {"date": end_date_str},
                "reminders": {"useDefault": False, "overrides": []},
            }
        else:
            event_body = {
                "summary": enriched_summary,
                "description": enriched_desc,
                "location": location,
                "visibility": "public",
                "colorId": color_id,
                "start": {
                    "dateTime": start_dt.isoformat(),
                    "timeZone": config.TIMEZONE,
                },
                "end": {
                    "dateTime": end_dt.isoformat(),
                    "timeZone": config.TIMEZONE,
                },
                "reminders": {"useDefault": False, "overrides": []},
            }

        try:
            logger.info(f"Enviando a Google API: {event_body}")
            event = (
                self.service.events()
                .insert(
                    calendarId=self.calendar_id,
                    body=event_body,
                    sendUpdates="none",
                )
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
                    sendUpdates="none",
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
    description = event.get("description", "")
    location = event.get("location", "")
    now = datetime.now(TZ)
    is_past = False

    # Extraer metadatos de la descripción si existen
    prio_label = ""
    cat_label = ""
    clean_desc = description
    if "--- METADATA ---" in description:
        lines = description.split("\n")
        for line in lines:
            if "PRIORIDAD:" in line:
                prio = line.split("PRIORIDAD:")[1].strip().lower()
                prio_map = {"alta": "🔴 Alta", "media": "🟡 Media", "baja": "🟢 Baja"}
                prio_label = prio_map.get(prio, "")
            elif "CATEGORIA:" in line:
                cat = line.split("CATEGORIA:")[1].strip().lower()
                cat_label = f"#{cat}"
        # Limpiar descripción para mostrar solo el contenido real
        if "--- METADATA ---" in description:
            parts = description.split("--- METADATA ---")
            if len(parts) > 1:
                # El contenido suele estar después de la metadata o antes si el orden cambia
                # En nuestro caso lo pusimos después.
                clean_desc = parts[1].split("\n", 3)[-1].strip()

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
    
    # Construir bloque de detalles
    details = []
    if prio_label: details.append(f"❗ *Prio:* {prio_label}")
    if cat_label: details.append(f"🏷️ {cat_label}")
    if location:
        # Codificar ubicación para URL de Maps
        import urllib.parse
        loc_encoded = urllib.parse.quote(location)
        details.append(f"📍 [Ver Mapa](https://www.google.com/maps/search/?api=1&query={loc_encoded})")
    
    details_str = ("\n  " + " | ".join(details)) if details else ""
    desc_line = f"\n📝 {clean_desc}" if clean_desc else ""

    return f"• *{summary}*{past_marker}\n  {when}{details_str}{desc_line}"
