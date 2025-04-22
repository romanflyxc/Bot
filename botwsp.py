from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from dotenv import load_dotenv
import os
import datetime
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Cargar variables de entorno desde .env
load_dotenv()

# Crear app Flask
app = Flask(__name__)

# Puerto que Render asigna dinámicamente
port = int(os.environ.get("PORT", 5000))

# Instanciar modelo LLM desde Groq
llama = ChatGroq(model="llama3-70b-8192")

# Google Calendar setup
SCOPES = ['https://www.googleapis.com/auth/calendar']
service_account_info = json.loads(os.environ['GOOGLE_CREDENTIALS_JSON'])
credentials = service_account.Credentials.from_service_account_info(
    service_account_info, scopes=SCOPES
)
calendar_service = build('calendar', 'v3', credentials=credentials)
CALENDAR_ID = "botgonza@group.calendar.google.com"  # ID de tu calendario

# Estado temporal
reservas_pendientes = {}

@app.route("/")
def home():
    return "✅ Bot activo"

@app.route("/whatsapp", methods=['POST'])
def whatsapp_reply():
    try:
        user_msg = request.form.get('Body').strip().lower()
        user_number = request.form.get('From')

        twilio_response = MessagingResponse()

        # Responder a "hola" directamente
        if "hola" in user_msg:
            twilio_response.message("¡Hola! Bienvenido a Canchas de Futbol Litoral. ¿En qué puedo ayudarte hoy?")
            return str(twilio_response)

        # Salir de la lógica de reserva si el usuario lo solicita
        if "salir" in user_msg or "cancelar" in user_msg:
            reservas_pendientes.pop(user_number, None)
            twilio_response.message("❌ Tu reserva ha sido cancelada. ¿Hay algo más en lo que te pueda ayudar?")
            return str(twilio_response)

        # Lógica para manejar la reserva de cancha
        if user_number in reservas_pendientes:
            if any(x in user_msg for x in ["sí", "confirmo", "confirmar", "dale", "ok"]):
                datos = reservas_pendientes.pop(user_number)
                start_dt = datos["start"]
                end_dt = datos["end"]
                evento = {
                    'summary': f"Reserva Cancha {datos['cancha']} - {datos['nombre']}",
                    'start': {'dateTime': start_dt.isoformat(), 'timeZone': 'America/Argentina/Buenos_Aires'},
                    'end': {'dateTime': end_dt.isoformat(), 'timeZone': 'America/Argentina/Buenos_Aires'},
                    'description': f"Reserva para {datos['nombre']} en cancha {datos['cancha']}"
                }
                calendar_service.events().insert(calendarId=CALENDAR_ID, body=evento).execute()
                twilio_response.message(f"✅ ¡Listo! La cancha {datos['cancha']} quedó reservada para {datos['nombre']} el {datos['fecha']} a las {datos['hora']}.")
                return str(twilio_response)
            else:
                reservas_pendientes.pop(user_number)
                twilio_response.message("❌ Reserva cancelada. Si quieres intentarlo de nuevo, decímelo.")
                return str(twilio_response)

        # Lógica para extraer la información de la reserva, más flexible
        extraction_prompt = f"""
        Extrae del siguiente mensaje estos datos:
        - Nombre
        - Fecha (YYYY-MM-DD)
        - Hora (HH:MM en 24hs)
        - Número de cancha (1 a 3)
        Si la información no está completamente clara, responde con un mensaje pidiendo más detalles.
        Mensaje: "{user_msg}"
        """

        extraction_response = llama.invoke([HumanMessage(content=extraction_prompt)])
        print("🧠 Respuesta de LLM:", extraction_response.content)

        try:
            extracted = json.loads(extraction_response.content)
        except json.JSONDecodeError as e:
            print(f"❌ No se pudo parsear como JSON: {extraction_response.content}")
            twilio_response.message("❌ No entendí los datos que enviaste. Por favor, escribe algo como: 'Reservar cancha 2 para Juan el 23 de abril a las 18:00'")
            return str(twilio_response)

        # Verificar que todos los campos necesarios estén presentes
        required_fields = ["nombre", "fecha", "hora", "cancha"]
        if not all(field in extracted for field in required_fields):
            twilio_response.message("❌ Faltan algunos datos importantes. ¿Podrías decirme tu nombre, la fecha y la hora, y qué cancha te gustaría reservar?")
            return str(twilio_response)

        nombre = extracted["nombre"]
        fecha = extracted["fecha"]
        hora = extracted["hora"]
        cancha = extracted["cancha"]

        start_dt = datetime.datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M")
        end_dt = start_dt + datetime.timedelta(hours=1)

        # Verificar disponibilidad
        events = calendar_service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=start_dt.isoformat() + "Z",
            timeMax=end_dt.isoformat() + "Z",
            singleEvents=True
        ).execute()

        if len(events.get('items', [])) > 0:
            twilio_response.message(f"⛔ La cancha {cancha} no está disponible el {fecha} a las {hora}. ¿Quieres probar otro horario?")
            return str(twilio_response)

        reservas_pendientes[user_number] = {
            "nombre": nombre,
            "fecha": fecha,
            "hora": hora,
            "cancha": cancha,
            "start": start_dt,
            "end": end_dt
        }

        twilio_response.message(f"📅 Vas a reservar la cancha {cancha} para {nombre} el {fecha} a las {hora}. ¿Confirmás? (respondé 'sí' para confirmar)")
        return str(twilio_response)

    except Exception as e:
        print(f"❌ Error en /whatsapp: {e}")
        twilio_response.message("❌ Ocurrió un error en el sistema. Por favor, intenta nuevamente más tarde.")
        return str(twilio_response)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port)