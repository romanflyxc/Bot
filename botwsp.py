from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from datetime import datetime
from dotenv import load_dotenv
import os

# Cargar variables de entorno desde .env
load_dotenv()

# Crear app Flask
app = Flask(__name__)

# Puerto que Render asigna dinámicamente
port = int(os.environ.get("PORT", 10000))

# Simular base de datos en memoria para sesiones de usuario
user_sessions = {}

# Instanciar modelo LLM desde Groq
llama = ChatGroq(model="llama3-70b-8192")

# Función ficticia para verificar disponibilidad en Google Calendar
def verificar_disponibilidad(fecha, hora):
    # Aquí deberías integrar la API de Google Calendar para verificar la disponibilidad
    # Por ejemplo, hacer una consulta para ver si ya hay un evento en esa fecha y hora.
    return True  # Asumimos que siempre está disponible

# Función ficticia para agregar una reserva a Google Calendar
def guardar_en_calendario(nombre, fecha, hora, cancha):
    # Aquí debes integrar la API de Google Calendar para guardar el evento
    print(f"Guardando en Google Calendar: {nombre} reserva la cancha {cancha} el {fecha} a las {hora}")

@app.route("/")
def home():
    return "✅ Bot de WhatsApp activo y esperando mensajes."

@app.route("/whatsapp", methods=['POST'])
def whatsapp_reply():
    try:
        # Obtener mensaje del usuario desde WhatsApp
        incoming_msg = request.values.get('Body', '').strip().lower()
        from_number = request.values.get('From', '')
        print(f"📩 Mensaje recibido de {from_number}: {incoming_msg}")

        # Si el usuario no tiene una sesión, inicializarla
        session = user_sessions.get(from_number, {
            'state': 'inicio',
            'nombre': None,
            'fecha': None,
            'hora': None,
            'cancha': None
        })

        respuesta = ""

        if session['state'] == 'inicio':
            if 'reservar' in incoming_msg:
                session['state'] = 'esperando_nombre'
                respuesta = "¡Genial! Empecemos con la reserva. ¿Cuál es tu nombre?"
            else:
                respuesta = "¡Hola! 👋 Bienvenido a Canchas de Futbol Litoral. ¿Querés hablar con alguien o hacer una reserva? Si querés reservar, escribí *reservar*."

        elif session['state'] == 'esperando_nombre':
            session['nombre'] = incoming_msg.title()
            session['state'] = 'esperando_fecha'
            respuesta = f"Gracias {session['nombre']}. ¿Para qué fecha querés reservar? (Ejemplo: 25/04/2025)"

        elif session['state'] == 'esperando_fecha':
            try:
                fecha_obj = datetime.strptime(incoming_msg, '%d/%m/%Y')
                session['fecha'] = fecha_obj.strftime('%Y-%m-%d')
                session['state'] = 'esperando_hora'
                respuesta = "¿Y a qué hora? (Ejemplo: 18:00)"
            except ValueError:
                respuesta = "❌ Formato de fecha inválido. Escribilo como: 25/04/2025"

        elif session['state'] == 'esperando_hora':
            try:
                datetime.strptime(incoming_msg, '%H:%M')
                session['hora'] = incoming_msg
                session['state'] = 'esperando_cancha'
                respuesta = "Perfecto. ¿Qué cancha querés reservar? Escribí 1, 2 o 3."
            except ValueError:
                respuesta = "❌ Formato de hora inválido. Escribilo como: 18:00"

        elif session['state'] == 'esperando_cancha':
            if incoming_msg in ['1', '2', '3']:
                session['cancha'] = incoming_msg
                # Verificar si la cancha está disponible
                disponibilidad = verificar_disponibilidad(session['fecha'], session['hora'])
                if disponibilidad:
                    respuesta = f"✅ Te reservo la cancha {session['cancha']} para el {session['fecha']} a las {session['hora']} a nombre de {session['nombre']}. ¿Confirmás?"
                    session['state'] = 'esperando_confirmacion'
                else:
                    respuesta = "❌ Esa fecha y hora ya están ocupadas. ¿Te gustaría elegir otro horario?"
            else:
                respuesta = "❌ Por favor escribí 1, 2 o 3 para elegir la cancha."

        elif session['state'] == 'esperando_confirmacion':
            if 'sí' in incoming_msg or 'si' in incoming_msg or 'confirmo' in incoming_msg:
                guardar_en_calendario(session['nombre'], session['fecha'], session['hora'], session['cancha'])
                respuesta = "🎉 ¡Reserva confirmada! Gracias por usar Canchas de Futbol Litoral."
                session = {'state': 'inicio', 'nombre': None, 'fecha': None, 'hora': None, 'cancha': None}
            else:
                respuesta = "❌ Reserva cancelada. Si querés intentarlo de nuevo, escribí *reservar*."
                session = {'state': 'inicio', 'nombre': None, 'fecha': None, 'hora': None, 'cancha': None}

        # Guardar la sesión del usuario
        user_sessions[from_number] = session

        # Enviar la respuesta por WhatsApp
        twilio_response = MessagingResponse()
        twilio_response.message(respuesta)

        return str(twilio_response), 200

    except Exception as e:
        print(f"❌ Error en /whatsapp: {e}")
        return "❌ Error interno del bot", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port)