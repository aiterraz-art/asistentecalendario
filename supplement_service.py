import json
import os
import logging
import uuid
from datetime import datetime
from typing import List, Dict
import pytz
import config

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "supplements.json")
TZ = pytz.timezone(config.TIMEZONE)

class SupplementService:
    def __init__(self):
        self._ensure_db()

    def _ensure_db(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        if not os.path.exists(DB_PATH):
            with open(DB_PATH, "w") as f:
                json.dump([], f)

    def _load(self) -> List[Dict]:
        try:
            with open(DB_PATH, "r") as f:
                data = json.load(f)
                # Migración: asegurar que todos tengan un ID
                changed = False
                for s in data:
                    if "id" not in s:
                        s["id"] = str(uuid.uuid4())[:8]
                        changed = True
                if changed:
                    self._save(data)
                return data
        except Exception as e:
            logger.error(f"Error cargando suplementos: {e}")
            return []

    def _save(self, data: List[Dict]):
        try:
            with open(DB_PATH, "w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logger.error(f"Error guardando suplementos: {e}")

    def add_supplement(self, name: str, time_str: str):
        """Añade un nuevo recordatorio de suplemento.
        
        Args:
            name: Nombre del suplemento.
            time_str: Hora en formato HH:MM.
        """
        data = self._load()
        # Verificar si ya existe para evitar duplicados exactos
        for s in data:
            if s["name"].lower() == name.lower() and s["time"] == time_str:
                return False
        
        data.append({
            "id": str(uuid.uuid4())[:8],
            "name": name,
            "time": time_str,
            "last_taken_date": None, # 'YYYY-MM-DD'
            "active": True,
            "next_reminder": None # Para el sistema de 'nagging' (reintentos)
        })
        self._save(data)
        return True

    def get_all(self) -> List[Dict]:
        return self._load()

    def mark_as_taken(self, names: List[str], date_str: str):
        """Marca varios suplementos como tomados para una fecha."""
        data = self._load()
        names_lower = [n.lower() for n in names]
        for s in data:
            if s["name"].lower() in names_lower:
                s["last_taken_date"] = date_str
                s["next_reminder"] = None
        self._save(data)

    def mark_as_taken_by_time(self, time_str: str, date_str: str):
        """Marca todos los suplementos de una hora específica como tomados."""
        data = self._load()
        for s in data:
            if s["time"] == time_str:
                s["last_taken_date"] = date_str
                s["next_reminder"] = None
        self._save(data)

    def set_next_reminder(self, names: List[str], next_dt_iso: str):
        """Programa el próximo reintento para un grupo de suplementos."""
        data = self._load()
        names_lower = [n.lower() for n in names]
        for s in data:
            if s["name"].lower() in names_lower:
                s["next_reminder"] = next_dt_iso
        self._save(data)

    def set_next_reminder_by_time(self, time_str: str, next_dt_iso: str):
        """Programa el próximo reintento para todos los suplementos de una hora."""
        data = self._load()
        for s in data:
            if s["time"] == time_str:
                s["next_reminder"] = next_dt_iso
        self._save(data)

    def get_pending(self, current_time: str, current_date: str) -> List[Dict]:
        """Obtiene suplementos que deben tomarse ahora y no han sido tomados."""
        data = self._load()
        pending = []
        now_aware = datetime.now(TZ)
        
        for s in data:
            if not s.get("active", True):
                continue
            
            # Caso 1: Hora exacta o pasada hoy, y no tomado hoy
            # Robusto: si current_time >= s["time"] y no tiene next_reminder y no ha sido tomado
            if s["last_taken_date"] != current_date:
                # Si no hay reintento programado, ver si ya pasó su hora hoy
                if not s.get("next_reminder"):
                    if current_time >= s["time"]:
                        pending.append(s)
                else:
                    # Si HAY reintento, ver si ya venció
                    try:
                        next_rem = datetime.fromisoformat(s["next_reminder"])
                        if next_rem.tzinfo is None:
                            next_rem = TZ.localize(next_rem)
                            
                        if now_aware >= next_rem:
                            pending.append(s)
                    except Exception as e:
                        logger.error(f"Error parsing next_reminder for {s.get('name')}: {e}")
            
        return pending

