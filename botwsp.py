from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv
import os
import datetime
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
import re

# Cargar variables de entorno desde .env
load_dotenv()

app = Flask(__name__)
port = int(os.environ.get("PORT", 10000))
llama = ChatGroq(model="llama3-70b-8192")

# Google Calendar setup
SCOPES = ['https://www.googleapis.com/auth/calendar']
service_account_info = json.loads(os.environ['GOOGLE_CREDENTIALS_JSON'])
credentials = service_account.Credentials.from_service_account_info(
    service_account_info, scopes=SCOPES
)
calendar_service = build('calendar', 'v3', credentials=credentials)
CALENDAR_ID = "botgonza@group.calendar.google.com"

reservas_pendientes = {}
contexto_usuario = {}


def verificar_disponibilidad(start_datetime, end_datetime, calendar_id=CALENDAR_ID):
    events = calendar_service.events().list(
        calendarId=calendar_id,
        timeMin=start_datetime.isoformat() + "Z",
        timeMax=end_datetime.isoformat() + "Z",
        singleEvents=True
    ).execute()
    return len(events.get('items', [])) == 0


def crear_evento(nombre, cancha, start_datetime, end_datetime):
    evento = {
        'summary': f"Reserva Cancha {cancha} - {nombre}",
        'start': {'dateTime': start_datetime.isoformat(), 'timeZone': 'America/Argentina/Buenos_Aires'},
        'end': {'dateTime': end_datetime.isoformat(), 'timeZone': 'America/Argentina/Buenos_Aires'},
        'description': f"Reserva para {nombre} en cancha {cancha}"
    }
    calendar_service.events().insert(calendarId=CALENDAR_ID, body=evento).execute()


@app.route("/")
def home():
    return "✅ Bot activo"


def normalizar_fecha(fecha_str):
    try:
        fecha_str = fecha_str.lower().replace("de", "")
        meses = {
            "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
            "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
        }
        partes = fecha_str.strip().split()
        if len(partes) == 2:
            dia = int(partes[0])
            mes = meses.get(partes[1])
            año = datetime.datetime.now().year
            return datetime.date(año, mes, dia).isoformat()
    except:
        return None


@app.route("/whatsapp", methods=['POST'])
def whatsapp_reply():
    try:
        user_msg = request.form.get('Body').strip().lower()
        user_number = request.form.get('From')
        twilio_response = MessagingResponse()

        # Saludo básico
        if user_msg in ["hola", "buenas", "holaa"]:
            twilio_response.message("¡Hola! Bienvenido a Canchas de Futbol Litoral. ¿En qué puedo ayudarte hoy?")
            return str(twilio_response)

        # Confirmación de reserva
        if user_number in reservas_pendientes:
            if any(x in user_msg for x in ["sí", "confirmo", "confirmar", "dale", "ok"]):
                datos = reservas_pendientes.pop(user_number)
                crear_evento(datos["nombre"], datos["cancha"], datos["start"], datos["end"])
                twilio_response.message(
                    f"✅ ¡Listo! La cancha {datos['cancha']} quedó reservada para {datos['nombre']} el {datos['fecha']} a las {datos['hora']}."
                )
                return str(twilio_response)
            else:
                reservas_pendientes.pop(user_number)
                twilio_response.message("❌ Reserva cancelada. Si querés intentarlo de nuevo, decímelo.")
                return str(twilio_response)

        # Acumulador de intención
        if user_number not in contexto_usuario:
            contexto_usuario[user_number] = {}

        datos = contexto_usuario[user_number]

        # Intentar extraer datos manualmente
        if "cancha" not in datos:
            match = re.search(r"cancha\s*(\d)", user_msg)
            if match:
                datos["cancha"] = int(match.group(1))

        if "nombre" not in datos:
            match = re.search(r"(?:soy|nombre)\s*(\w+)", user_msg)
            if match:
                datos["nombre"] = match.group(1).capitalize()
            elif len(user_msg.split()) == 1:
                datos["nombre"] = user_msg.capitalize()

        if "fecha" not in datos:
            match = re.search(r"(\d{1,2}\s+de\s+\w+)", user_msg)
            if match:
                fecha = normalizar_fecha(match.group(1))
                if fecha:
                    datos["fecha"] = fecha

        if "hora" not in datos:
            match = re.search(r"(\d{1,2})([:.]?(\d{2}))?\s*(hs|horas)?", user_msg)
            if match:
                hora = match.group(1).zfill(2) + ":" + (match.group(3) or "00")
                datos["hora"] = hora

        if all(k in datos for k in ["nombre", "fecha", "hora", "cancha"]):
            start_dt = datetime.datetime.strptime(f"{datos['fecha']} {datos['hora']}", "%Y-%m-%d %H:%M")
            end_dt = start_dt + datetime.timedelta(hours=1)

            if not verificar_disponibilidad(start_dt, end_dt):
                twilio_response.message("⛔ Esa cancha no está disponible en ese horario. ¿Querés probar con otra?")
                return str(twilio_response)

            reservas_pendientes[user_number] = {
                **datos,
                "start": start_dt,
                "end": end_dt
            }
            contexto_usuario.pop(user_number)

            twilio_response.message(
                f"📅 Vas a reservar la cancha {datos['cancha']} para {datos['nombre']} el {datos['fecha']} a las {datos['hora']}. ¿Confirmás? (respondé 'sí')"
            )
            return str(twilio_response)

        # Si aún no tenemos todos los datos necesarios
        twilio_response.message("📋 Para hacer la reserva necesito: tu nombre, fecha, hora y número de cancha. ¿Podés enviármelo?")
        return str(twilio_response)

    except Exception as e:
        print(f"❌ Error en /whatsapp: {e}")
        return "❌ Error interno del bot", 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port)
