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

# Cargar variables de entorno desde .env
load_dotenv()

app = Flask(__name__)
port = int(os.environ.get("PORT", 5000))
llama = ChatGroq(model="llama3-70b-8192")

# Google Calendar setup
SCOPES = ['https://www.googleapis.com/auth/calendar']
service_account_info = json.loads(os.environ['GOOGLE_CREDENTIALS_JSON'])
credentials = service_account.Credentials.from_service_account_info(
    service_account_info, scopes=SCOPES
)
calendar_service = build('calendar', 'v3', credentials=credentials)
# Usamos el calendario "botgonza" para las reservas
CALENDAR_ID = "botgonza@group.calendar.google.com"  # ID de tu calendario

# Estado temporal
reservas_pendientes = {}

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

@app.route("/whatsapp", methods=['POST'])
def whatsapp_reply():
    try:
        user_msg = request.form.get('Body').strip().lower()
        user_number = request.form.get('From')

        twilio_response = MessagingResponse()

        # Paso 2: Confirmación
        if user_number in reservas_pendientes:
            if any(x in user_msg for x in ["sí", "confirmo", "confirmar", "dale", "ok"]):
                datos = reservas_pendientes.pop(user_number)
                crear_evento(datos["nombre"], datos["cancha"], datos["start"], datos["end"])
                twilio_response.message(f"✅ ¡Listo! La cancha {datos['cancha']} quedó reservada para {datos['nombre']} el {datos['fecha']} a las {datos['hora']}.")
                return str(twilio_response)
            else:
                reservas_pendientes.pop(user_number)
                twilio_response.message("❌ Reserva cancelada. Si querés intentarlo de nuevo, decímelo.")
                return str(twilio_response)

        # Paso 1: Extracción de datos
        extraction_prompt = f"""
        Extrae del siguiente mensaje estos datos:
        - Nombre
        - Fecha (YYYY-MM-DD)
        - Hora (HH:MM en 24hs)
        - Número de cancha (1 a 3)
        Responde en JSON como este ejemplo:
        {{
            "nombre": "Juan",
            "fecha": "2025-04-23",
            "hora": "18:00",
            "cancha": 2
        }}
        Mensaje: "{user_msg}"
        """

        extraction_response = llama.invoke([HumanMessage(content=extraction_prompt)])
        extracted = json.loads(extraction_response.content)

        nombre = extracted["nombre"]
        fecha = extracted["fecha"]
        hora = extracted["hora"]
        cancha = extracted["cancha"]

        start_dt = datetime.datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M")
        end_dt = start_dt + datetime.timedelta(hours=1)

        disponible = verificar_disponibilidad(start_dt, end_dt)

        if not disponible:
            canchas_disponibles = []
            for nro in [1, 2, 3]:
                if nro == cancha:
                    continue
                if verificar_disponibilidad(start_dt, end_dt):
                    desc = f"Cancha {nro}"
                    if nro == 2:
                        desc += " (la del medio)"
                    canchas_disponibles.append(desc)

            if canchas_disponibles:
                disponibles_str = ", ".join(canchas_disponibles)
                twilio_response.message(
                    f"⛔ La cancha {cancha} no está disponible el {fecha} a las {hora}. "
                    f"Pero las siguientes están libres: {disponibles_str}. ¿Querés reservar una de esas?"
                )
            else:
                twilio_response.message(
                    f"⛔ Ninguna cancha está disponible el {fecha} a las {hora}. ¿Querés probar otro horario?"
                )
            return str(twilio_response)

        # Guardar para confirmar
        reservas_pendientes[user_number] = {
            "nombre": nombre,
            "fecha": fecha,
            "hora": hora,
            "cancha": cancha,
            "start": start_dt,
            "end": end_dt
        }

        twilio_response.message(
            f"📅 Vas a reservar la cancha {cancha} para {nombre} el {fecha} a las {hora}. ¿Confirmás? (respondé 'sí' para confirmar)"
        )
        return str(twilio_response)

    except Exception as e:
        print(f"❌ Error en /whatsapp: {e}")
        return "❌ Error interno del bot", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port)