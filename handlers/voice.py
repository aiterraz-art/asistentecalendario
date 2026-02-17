"""Handler para mensajes de voz — transcripción y procesamiento con NLP."""

import logging
import os
import tempfile
from telegram import Update
from telegram.ext import ContextTypes

from nlp_processor import parse_voice_message
from handlers.natural_language import (
    handle_crear,
    handle_listar,
    handle_eliminar,
    handle_completar,
    handle_consultar,
)

logger = logging.getLogger(__name__)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Descarga el audio y lo procesa con Gemini."""
    voice = update.message.voice
    if not voice:
        return

    # Mostrar que estamos procesando
    processing_msg = await update.message.reply_text("🎧 Escuchando tu mensaje...")

    try:
        # 1. Descargar el archivo a un temporal
        with tempfile.NamedTemporaryFile(suffix=".oga", delete=False) as tmp:
            tmp_path = tmp.name

        file = await context.bot.get_file(voice.file_id)
        await file.download_to_drive(tmp_path)

        # 2. Procesar con Gemini (Audio NLP)
        try:
            result = parse_voice_message(tmp_path)
        finally:
            # Limpiar archivo temporal
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

        # 3. Extraer intención y datos
        intencion = result.get("intencion", "otro")
        datos = result.get("datos", {})
        respuesta = result.get("respuesta", "")

        # 4. Delegar a los handlers de lenguaje natural (reutilización)
        if intencion == "crear":
            await handle_crear(update, context, processing_msg, datos, respuesta)
        elif intencion == "listar":
            await handle_listar(update, context, processing_msg, datos, respuesta)
        elif intencion == "eliminar":
            await handle_eliminar(update, context, processing_msg, datos, respuesta)
        elif intencion == "completar":
            await handle_completar(update, context, processing_msg, datos, respuesta)
        elif intencion == "consultar":
            await handle_consultar(update, context, processing_msg, datos, respuesta)
        else:
            await processing_msg.edit_text(
                respuesta or "Lo siento, escuché el audio pero no pude identificar qué quieres hacer. "
                "Prueba hablando más claro o enviando el texto."
            )

    except Exception as e:
        logger.error(f"Error procesando mensaje de voz: {e}")
        await processing_msg.edit_text("❌ Tuve un problema al procesar el audio. Intenta de nuevo.")
