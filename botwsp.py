from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from dotenv import load_dotenv
import os

# Cargar variables de entorno desde .env
load_dotenv()

# Crear app Flask
app = Flask(__name__)

# Puerto que Render asigna dinámicamente
port = int(os.environ.get("PORT", 5000))

@app.route("/")
def home():
    return "✅ Bot de WhatsApp activo y esperando mensajes."

# Instanciar modelo LLM desde Groq
llama = ChatGroq(model="llama3-70b-8192")

@app.route("/whatsapp", methods=['POST'])
def whatsapp_reply():
    try:
        # Obtener mensaje del usuario desde WhatsApp
        user_msg = request.form.get('Body')
        user_number = request.form.get('From')
        print(f"📩 Mensaje recibido de {user_number}: {user_msg}")

        # Construir contexto para el LLM
        messages = [
            SystemMessage(content="""
                Eres Litory, asistente virtual de Canchas de Futbol Litoral. 
                Tu tarea es tomar reservas, no contestes preguntas que no sean sobre reservas o las instalaciones. 
                Responde de forma amable, profesional y en menos de 2 oraciones.
                No menciones que eres una IA.
            """),
            HumanMessage(content=user_msg)
        ]

        # Obtener respuesta del modelo
        response = llama.invoke(messages)
        bot_reply = response.content  # ✅ corregido: no usar subscript

        # Enviar respuesta por WhatsApp
        twilio_response = MessagingResponse()
        twilio_response.message(bot_reply)

        return str(twilio_response)
    
    except Exception as e:
        print(f"❌ Error en /whatsapp: {e}")
        return "❌ Error interno del bot", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port)