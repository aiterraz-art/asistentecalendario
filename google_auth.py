"""Autenticación OAuth 2.0 con Google Calendar."""

import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

import config


def get_credentials() -> Credentials:
    """Obtiene o refresca las credenciales de Google Calendar.
    Prioriza variables de entorno para entornos cloud.
    """
    creds = None

    # 1. Intentar cargar token desde variable de entorno (JSON string)
    if config.GOOGLE_TOKEN_JSON:
        import json
        info = json.loads(config.GOOGLE_TOKEN_JSON)
        creds = Credentials.from_authorized_user_info(info, config.GOOGLE_SCOPES)

    # 2. Si no, intentar cargar token desde archivo físico (local)
    elif os.path.exists(config.GOOGLE_TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(
            config.GOOGLE_TOKEN_FILE, config.GOOGLE_SCOPES
        )

    # 3. Si no hay credenciales válidas o expiraron, obtener nuevas
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Intentar cargar credenciales de cliente (client secrets)
            client_config = None
            if config.GOOGLE_CREDENTIALS_JSON:
                import json
                client_config = json.loads(config.GOOGLE_CREDENTIALS_JSON)
            
            if client_config:
                flow = InstalledAppFlow.from_client_config(
                    client_config, config.GOOGLE_SCOPES
                )
            elif os.path.exists(config.GOOGLE_CREDENTIALS_FILE):
                flow = InstalledAppFlow.from_client_secrets_file(
                    config.GOOGLE_CREDENTIALS_FILE, config.GOOGLE_SCOPES
                )
            else:
                raise FileNotFoundError(
                    "No se encontraron credenciales de Google. Configura GOOGLE_CREDENTIALS_JSON o el archivo físico."
                )
            
            creds = flow.run_local_server(port=0)

        # Solo guardamos a archivo si no estamos usando variables de entorno
        if not config.GOOGLE_TOKEN_JSON:
            with open(config.GOOGLE_TOKEN_FILE, "w") as token_file:
                token_file.write(creds.to_json())

    return creds


def get_calendar_service():
    """Devuelve un servicio autenticado de Google Calendar API."""
    creds = get_credentials()
    return build("calendar", "v3", credentials=creds)
