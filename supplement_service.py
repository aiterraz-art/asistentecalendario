import json
import os
import logging
from datetime import datetime
from typing import List, Dict

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "supplements.json")

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
                return json.load(f)
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
                s["next_reminder"] = None # Limpiar reintento si lo había
        self._save(data)

    def set_next_reminder(self, names: List[str], next_dt_iso: str):
        """Programa el próximo reintento para un grupo de suplementos."""
        data = self._load()
        names_lower = [n.lower() for n in names]
        for s in data:
            if s["name"].lower() in names_lower:
                s["next_reminder"] = next_dt_iso
        self._save(data)

    def get_pending(self, current_time: str, current_date: str) -> List[Dict]:
        """Obtiene suplementos que deben tomarse ahora y no han sido tomados."""
        data = self._load()
        pending = []
        for s in data:
            if not s.get("active", True):
                continue
            
            # Caso 1: Hora exacta y no tomado hoy
            if s["time"] == current_time and s["last_taken_date"] != current_date:
                pending.append(s)
            
            # Caso 2: Tiene un 'next_reminder' que ya pasó
            elif s.get("next_reminder"):
                try:
                    next_rem = datetime.fromisoformat(s["next_reminder"])
                    if datetime.now() >= next_rem and s["last_taken_date"] != current_date:
                        pending.append(s)
                except:
                    pass
        return pending
