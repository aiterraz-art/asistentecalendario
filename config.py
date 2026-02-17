"""Configuración central del bot."""

import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Google Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Google Calendar
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON", "") # Para Railway/Render
GOOGLE_TOKEN_JSON = os.getenv("GOOGLE_TOKEN_JSON", "")           # Para Railway/Render
GOOGLE_TOKEN_FILE = "token.json"
GOOGLE_SCOPES = ["https://www.googleapis.com/auth/calendar"]

# Seguridad
AUTHORIZED_USER_ID = os.getenv("AUTHORIZED_USER_ID", "")

# Zona horaria
TIMEZONE = os.getenv("TIMEZONE", "America/Argentina/Buenos_Aires")
