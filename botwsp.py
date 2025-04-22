from flask import Flask, request
from datetime import datetime
import os
import json

app = Flask(__name__)

# Memoria temporal para guardar el estado de cada usuario
user_sessions = {}

def guardar_en_calendario(nombre, fecha, hora, cancha):
    # Esta función debería agregar el evento a Google Calendar
    print(f"📅 Evento: {nombre}, {fecha}, {hora}, Cancha {cancha}")
    # Aquí iría la lógica real usando Google Calendar API
    return True

@app.route('/whatsapp', methods=['POST'])
def whatsapp_reply():
    try:
        incoming_msg = request.values.get('Body', '').strip().lower()
        from_number = request.values.get('From', '')

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
                respuesta = f"✅ Te reservo la cancha {session['cancha']} para el {session['fecha']} a las {session['hora']} a nombre de {session['nombre']}. ¿Confirmás?"
                session['state'] = 'esperando_confirmacion'
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

        user_sessions[from_number] = session

        return respuesta, 200

    except Exception as e:
        print("Error en whatsapp_reply:", str(e))
        return "Ocurrió un error en el bot.", 500

@app.route('/')
def index():
    return "Bot de WhatsApp funcionando."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))