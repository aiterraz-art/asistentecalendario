# 📅 Bot Asistente de Agenda — Telegram + Google Calendar

Bot de Telegram que funciona como asistente personal de agenda, integrado con Google Calendar y con procesamiento de lenguaje natural vía Google Gemini.

## ✨ Funcionalidades

- **Crear eventos** con comando `/nuevo` (paso a paso) o con lenguaje natural
  - _"Reunión con Juan mañana a las 3pm"_
  - _"Dentista el viernes a las 10"_
- **Ver agenda** con `/agenda` (próximos 7 días) o `/hoy`
- **Eliminar eventos** con `/eliminar` o texto libre
- **Lenguaje natural** — escribí libremente y Gemini interpreta tu intención

## 🛠️ Requisitos

- Python 3.10+
- Token de bot de Telegram (vía [@BotFather](https://t.me/BotFather))
- Proyecto en Google Cloud con Calendar API habilitada
- API Key de Google Gemini ([Google AI Studio](https://aistudio.google.com/apikey))

## 🚀 Instalación

### 1. Clonar e instalar dependencias

```bash
cd "Bot calendario"
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configurar Google Calendar API

1. Ir a [Google Cloud Console](https://console.cloud.google.com/)
2. Crear un proyecto nuevo (o usar uno existente)
3. Habilitar **Google Calendar API**
4. Ir a **Credenciales** → Crear credenciales → **ID de cliente OAuth 2.0**
   - Tipo: **Aplicación de escritorio**
5. Descargar el archivo JSON y guardarlo como `credentials.json` en la carpeta del proyecto

### 3. Configurar variables de entorno

```bash
cp .env.example .env
```

Editar `.env` con tus valores:

```env
TELEGRAM_BOT_TOKEN=tu_token_de_botfather
GEMINI_API_KEY=tu_api_key_de_gemini
GOOGLE_CREDENTIALS_FILE=credentials.json
AUTHORIZED_USER_ID=tu_id_de_telegram
TIMEZONE=America/Argentina/Buenos_Aires
```

> 💡 Para obtener tu ID de Telegram, iniciá el bot con `/start` y te lo mostrará.

### 4. Ejecutar el bot

```bash
python bot.py
```

La primera vez se abrirá un navegador para autorizar el acceso a Google Calendar. Esto genera un archivo `token.json` que se reutiliza automáticamente.

## 📱 Comandos

| Comando | Descripción |
|---------|-------------|
| `/start` | Bienvenida e instrucciones |
| `/nuevo` | Crear evento paso a paso |
| `/agenda` | Ver eventos de los próximos 7 días |
| `/hoy` | Ver eventos de hoy |
| `/eliminar` | Eliminar un evento |
| `/cancelar` | Cancelar operación en curso |

## 🗣️ Lenguaje Natural

Podés escribir directamente en el chat y Gemini interpreta tu intención:

- _"Agendar reunión de equipo el lunes a las 10am"_
- _"¿Qué tengo mañana?"_
- _"Borrá la cita del dentista"_
- _"Mostrame mi semana"_

## 📁 Estructura del Proyecto

```
├── bot.py                  # Entry point
├── config.py               # Configuración
├── google_auth.py          # Auth OAuth Google
├── calendar_service.py     # Google Calendar wrapper
├── nlp_processor.py        # NLP con Gemini
├── handlers/
│   ├── start.py            # /start
│   ├── create_event.py     # /nuevo (conversacional)
│   ├── list_events.py      # /agenda, /hoy
│   ├── delete_event.py     # /eliminar
│   └── natural_language.py # Texto libre → NLP
├── requirements.txt
├── .env.example
└── README.md
```
