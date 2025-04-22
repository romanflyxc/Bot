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

# Cargar variables de entorno
load_dotenv()

app = Flask(__name__)
port = int(os.environ.get("PORT", 10000))
llama = ChatGroq(model="llama3-70b-8192")

# Google Calendar setup
SCOPES = ['https://www.googleapis.com/auth/calendar']
service_account_info = json.loads(os.environ['GOOGLE_CREDENTIALS_JSON'])
credentials = service_account.Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
calendar_service = build('calendar', 'v3', credentials=credentials)
CALENDAR_ID = "botgonza@group.calendar.google.com"

# Estados temporales por usuario
estado_usuario = {}

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
    return "✅ Bot de WhatsApp activo"

@app.route("/whatsapp", methods=['POST'])
def whatsapp_reply():
    try:
        user_msg = request.form.get('Body').strip().lower()
        user_number = request.form.get('From')
        twilio_response = MessagingResponse()

        # Saludos
        if user_msg in ["hola", "buenas", "holaa", "hello"]:
            twilio_response.message("¡Hola! Bienvenido a Canchas de Futbol Litoral. ¿En qué puedo ayudarte hoy?")
            return str(twilio_response)

        # Confirmación de reserva
        if user_number in estado_usuario and estado_usuario[user_number].get("estado") == "esperando_confirmacion":
            if any(x in user_msg for x in ["sí", "confirmo", "dale", "ok"]):
                datos = estado_usuario.pop(user_number)
                crear_evento(datos["nombre"], datos["cancha"], datos["start"], datos["end"])
                twilio_response.message(f"✅ ¡Listo! Cancha {datos['cancha']} reservada para {datos['nombre']} el {datos['fecha']} a las {datos['hora']}.")
            else:
                estado_usuario.pop(user_number)
                twilio_response.message("❌ Reserva cancelada. Si querés intentarlo de nuevo, decímelo.")
            return str(twilio_response)

        # Obtener o inicializar estado del usuario
        datos = estado_usuario.get(user_number, {})

        # Intentar extraer info del mensaje
        extraction_prompt = f"""
        Extrae si podés estos datos del mensaje:
        - Nombre
        - Fecha (YYYY-MM-DD)
        - Hora (HH:MM)
        - Número de cancha (1 a 3)

        Respondé solo con el JSON como este ejemplo:
        {{
            "nombre": "Juan",
            "fecha": "2025-04-23",
            "hora": "18:00",
            "cancha": 2
        }}

        Mensaje: "{user_msg}"
        """

        extraction_response = llama.invoke([HumanMessage(content=extraction_prompt)])
        try:
            extra = json.loads(extraction_response.content)
            datos.update({k: v for k, v in extra.items() if v})
        except:
            pass

        estado_usuario[user_number] = datos

        # Ver qué datos faltan
        campos_faltantes = [campo for campo in ["nombre", "fecha", "hora", "cancha"] if campo not in datos]

        if campos_faltantes:
            texto = "📋 Para hacer la reserva necesito: "
            texto += ", ".join(campos_faltantes) + ". ¿Podés enviármelo?"
            twilio_response.message(texto)
            return str(twilio_response)

        # Convertir fecha y hora
        start_dt = datetime.datetime.strptime(f"{datos['fecha']} {datos['hora']}", "%Y-%m-%d %H:%M")
        end_dt = start_dt + datetime.timedelta(hours=1)

        disponible = verificar_disponibilidad(start_dt, end_dt)

        if not disponible:
            twilio_response.message(f"⛔ La cancha {datos['cancha']} no está disponible el {datos['fecha']} a las {datos['hora']}. ¿Querés probar otro horario o cancha?")
            return str(twilio_response)

        datos["start"] = start_dt
        datos["end"] = end_dt
        datos["estado"] = "esperando_confirmacion"
        estado_usuario[user_number] = datos

        twilio_response.message(f"📅 Vas a reservar la cancha {datos['cancha']} para {datos['nombre']} el {datos['fecha']} a las {datos['hora']}. ¿Confirmás?")
        return str(twilio_response)

    except Exception as e:
        print(f"❌ Error en /whatsapp: {e}")
        return "❌ Error interno del bot", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port)