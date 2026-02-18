"""Procesador de lenguaje natural con Google Gemini.

Interpreta mensajes del usuario para extraer intención y datos de eventos.
"""

import json
import logging
from datetime import datetime

import pytz
from google import genai

import config

logger = logging.getLogger(__name__)

TZ = pytz.timezone(config.TIMEZONE)

# Cliente de Gemini (se inicializa al primer uso)
_client = None
MODEL = "gemini-2.0-flash"


def _get_client():
    """Obtiene o crea el cliente de Gemini (lazy init)."""
    global _client
    if _client is None:
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client

SYSTEM_PROMPT = """Eres un asistente de agenda personal. Tu trabajo es interpretar mensajes del usuario
en español y extraer la intención y los datos relevantes.

La fecha y hora actual es: {current_datetime}
La zona horaria es: {timezone}

INTENCIONES POSIBLES:
- "crear": El usuario quiere crear un evento, reunión o tarea
- "listar": El usuario quiere ver sus eventos
- "eliminar": El usuario quiere borrar un evento
- "completar": El usuario quiere marcar algo como completado/terminado/hecho
- "consultar": El usuario hace una pregunta sobre su agenda
- "suplementacion": El usuario quiere agendar recordatorios diarios de medicamentos o suplementos. Si menciona varios para la misma hora, inclúyelos TODOS en la lista `suplementos`. (Ej: "tomar omega 3 y magnesio a las 7am").
- "otro": No está relacionado con la agenda

TIPOS DE EVENTO:
- "reunion": Tiene hora específica (ej: "reunión a las 3pm", "cita con el dentista a las 10")
- "tarea": NO tiene hora específica, es algo que hay que hacer durante el día (ej: "enviar pedido", "mejorar el prompt", "comprar materiales"). Las tareas SIEMPRE son de día completo.

DEBES responder SIEMPRE en formato JSON válido con esta estructura:
{{
    "intencion": "crear|listar|eliminar|completar|consultar|suplementacion|otro",
    "datos": {{
        "titulo": "título del evento (si aplica)",
        "tipo": "reunion|tarea",
        "fecha": "YYYY-MM-DD (si aplica)",
        "hora_inicio": "HH:MM (formato 24h, SOLO para reuniones y suplementos)",
        "hora_fin": "HH:MM (formato 24h, SOLO para reuniones, si no se especifica dejar null)",
        "descripcion": "descripción adicional (si aplica)",
        "dia_completo": true,
        "rango_dias": 7,
        "categoria": "personal|trabajo|salud|casa|otro",
        "prioridad": "alta|media|baja",
        "ubicacion": "nombre del lugar o dirección (si aplica)",
        "suplementos": ["lista", "de", "nombres", "(SOLO para suplementacion)"]
    }},
    "respuesta": "Una respuesta breve y amigable para el usuario sobre lo que entendiste"
}}

REGLAS IMPORTANTES:
- Si el usuario dice "mañana", calcula la fecha correcta
- Si dice "el lunes", "el martes", etc., calcula la próxima ocurrencia
- Si dice "próxima semana", "la semana que viene", calcula el lunes de la próxima semana
- Si el tipo es "tarea", SIEMPRE poner dia_completo en true y hora_inicio/hora_fin en null
- Si el tipo es "reunion" y tiene hora, poner dia_completo en false
- Si el tipo es "reunion" y NO tiene hora, poner dia_completo en true
- Si no especifica hora de fin, dejar hora_fin como null
- Si no se especifica fecha para una tarea, usar la fecha de HOY
- Para "listar", rango_dias indica cuántos días hacia adelante mostrar
- Para "completar", extraer el título de lo que completó en "titulo"
- **Prioridad**: "alta" si usa palabras como "urgente", "importante", "prioritario". "baja" si dice "cuando puedas", "no corre prisa". Por defecto "media".
- **Categoría**: Clasifica según el contexto (ej: dentista -> salud, oficina -> trabajo, supermercado -> casa). Por defecto "personal" si es ambiguo o "otro".
- **Ubicación**: Extrae nombres de lugares o direcciones físicas si se mencionan.
- Responde siempre en español
- NO incluyas explicaciones fuera del JSON
"""


def parse_user_message(message: str) -> dict:
    """Procesa un mensaje del usuario con Gemini y devuelve intención + datos.

    Returns:
        dict con claves: intencion, datos, respuesta
    """
    now = datetime.now(TZ)
    current_dt = now.strftime("%A %d de %B de %Y, %H:%M")

    prompt = SYSTEM_PROMPT.format(
        current_datetime=current_dt,
        timezone=config.TIMEZONE,
    )

    try:
        response = _get_client().models.generate_content(
            model=MODEL,
            contents=message,
            config=genai.types.GenerateContentConfig(
                system_instruction=prompt,
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )

        raw = response.text.strip()
        # Limpiar posibles bloques markdown
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        result = json.loads(raw)
        logger.info(f"NLP resultado: {result}")
        return result

    except json.JSONDecodeError as e:
        logger.error(f"Error parseando respuesta de Gemini: {e}\nRaw: {raw}")
        return {
            "intencion": "otro",
            "datos": {},
            "respuesta": "No pude entender bien tu mensaje. ¿Puedes reformularlo?",
        }
    except Exception as e:
        logger.error(f"Error en NLP: {e}")
        return {
            "intencion": "otro",
            "datos": {},
            "respuesta": "Hubo un error procesando tu mensaje. Intenta de nuevo.",
        }


def parse_voice_message(audio_file_path: str) -> dict:
    """Procesa un archivo de audio con Gemini y devuelve intención + datos.

    Args:
        audio_file_path: Ruta local al archivo de audio (ej: .ogg).

    Returns:
        dict con claves: intencion, datos, respuesta
    """
    now = datetime.now(TZ)
    current_dt = now.strftime("%A %d de %B de %Y, %H:%M")

    prompt = SYSTEM_PROMPT.format(
        current_datetime=current_dt,
        timezone=config.TIMEZONE,
    )

    try:
        # Leer el archivo de audio
        with open(audio_file_path, "rb") as f:
            audio_data = f.read()

        response = _get_client().models.generate_content(
            model=MODEL,
            contents=[
                {"inline_data": {"mime_type": "audio/ogg", "data": audio_data}},
                prompt,
            ],
            config=genai.types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )

        raw = response.text.strip()
        # Limpiar posibles bloques markdown
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        result = json.loads(raw)
        logger.info(f"NLP Audio resultado: {result}")
        return result

    except Exception as e:
        logger.error(f"Error procesando audio con Gemini: {e}")
        return {
            "intencion": "otro",
            "datos": {},
            "respuesta": "Lo siento, no pude procesar tu mensaje de voz correctamente.",
        }
