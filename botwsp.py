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
import traceback  # al principio del archivo

# Cargar variables de entorno
load_dotenv()

app = Flask(__name__)
port = int(os.environ.get("PORT", 10000))
llama = ChatGroq(model="llama3-70b-8192")

# Google Calendar
SCOPES = ['https://www.googleapis.com/auth/calendar']
service_account_info = json.loads(os.environ['GOOGLE_CREDENTIALS_JSON'])
credentials = service_account.Credentials.from_service_account_info(
    service_account_info, scopes=SCOPES
)
calendar_service = build('calendar', 'v3', credentials=credentials)
CALENDAR_ID = "botgonza@group.calendar.google.com"

# Estado temporal por usuario
estado_usuarios = {}

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

        # Saludo
        if user_msg in ["hola", "buenas", "buen día", "buenas tardes"]:
            twilio_response.message("¡Hola! Bienvenido a Canchas de Futbol Litoral. ¿En qué puedo ayudarte hoy?")
            return str(twilio_response)

        # Si hay reserva pendiente de confirmación
        if user_number in estado_usuarios and estado_usuarios[user_number].get("listo_para_confirmar"):
            if any(x in user_msg for x in ["sí", "confirmo", "dale", "ok"]):
                datos = estado_usuarios.pop(user_number)
                crear_evento(datos["nombre"], datos["cancha"], datos["start"], datos["end"])
                twilio_response.message(
                    f"✅ ¡Listo! La cancha {datos['cancha']} quedó reservada para {datos['nombre']} el {datos['fecha']} a las {datos['hora']}."
                )
            else:
                estado_usuarios.pop(user_number)
                twilio_response.message("❌ Reserva cancelada. Si querés intentarlo de nuevo, decímelo.")
            return str(twilio_response)

        # Inicializar estado si no existe
        if user_number not in estado_usuarios:
            estado_usuarios[user_number] = {}

        # Intentar completar info con LLM
        prompt = f"""
        Extraé del mensaje los siguientes datos si están presentes:
        - nombre
        - fecha (YYYY-MM-DD)
        - hora (HH:MM en 24h)
        - número de cancha (1, 2 o 3)

        Responde solo JSON:
        {{
            "nombre": "Juan",
            "fecha": "2025-04-23",
            "hora": "18:00",
            "cancha": 2
        }}

        Mensaje: "{user_msg}"
        """

        respuesta = llama.invoke([HumanMessage(content=prompt)])
        try:
            datos_extraidos = json.loads(respuesta.content)
            estado_usuarios[user_number].update(datos_extraidos)
        except:
            pass  # Si no pudo extraer, seguimos con lo anterior

        datos = estado_usuarios[user_number]
        campos_faltantes = [campo for campo in ["nombre", "fecha", "hora", "cancha"] if campo not in datos]

        if campos_faltantes:
            twilio_response.message("📋 Para hacer la reserva necesito: tu nombre, fecha, hora y número de cancha. ¿Podés enviármelo?")
            return str(twilio_response)

        # Si ya están todos los datos
        nombre = datos["nombre"]
        fecha = datos["fecha"]
        hora = datos["hora"]
        cancha = datos["cancha"]

        start_dt = datetime.datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M")
        end_dt = start_dt + datetime.timedelta(hours=1)

        disponible = verificar_disponibilidad(start_dt, end_dt)

        if not disponible:
            twilio_response.message(f"⛔ La cancha {cancha} no está disponible el {fecha} a las {hora}. ¿Querés probar otro horario o cancha?")
            return str(twilio_response)

        # Guardar datos confirmación
        datos.update({
            "start": start_dt,
            "end": end_dt,
            "listo_para_confirmar": True
        })

        twilio_response.message(f"📅 Vas a reservar la cancha {cancha} para {nombre} el {fecha} a las {hora}. ¿Confirmás?")
        return str(twilio_response)

    except Exception as e:
        print("❌ Error en /whatsapp:")
        traceback.print_exc()  # Esto imprimirá la traza completa del error
        return "❌ Error interno del bot", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port)