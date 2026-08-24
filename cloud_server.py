"""
Servidor Cloud 24/7 de Blitzo (Blitzo Cloud Hub).

Diseñado para correr en plataformas de hosting gratuitas (Render, Koyeb, Railway, Fly.io):
  - Activo 24/7 aunque la PC esté apagada o cerrada.
  - La app móvil se conecta a https://tu-servidor-cloud.onrender.com
  - Conexión con Gemini API para chat, notas y triage de WhatsApp en tiempo real.
  - Cola de comandos diferidos para la PC (cuando la PC se encienda, descarga las tareas pendientes).
"""
import os
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.parse
from typing import Dict, Any, List
import requests

PORT = int(os.environ.get("PORT", 8765))
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
USER_NAME = os.environ.get("USER_NAME", "Juan")

# Memoria de conversación y cola de comandos en la nube
chat_history: List[Dict[str, Any]] = []
pending_pc_commands: List[Dict[str, Any]] = []
pending_mobile_replies: List[Dict[str, Any]] = []
pc_last_seen = 0.0


def call_gemini(prompt: str, system_prompt: str = "") -> str:
    """Llama a la API de Gemini directamente desde el servidor Cloud."""
    api_key = GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return "Error: No se ha configurado GEMINI_API_KEY en las variables de entorno del servidor Cloud."

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    
    contents = []
    if system_prompt:
        contents.append({"role": "user", "parts": [{"text": f"System Directive: {system_prompt}"}]})
        contents.append({"role": "model", "parts": [{"text": "Entendido. Operando bajo estas directivas."}]})

    # Agregar historial reciente
    for turn in chat_history[-6:]:
        contents.append({"role": turn["role"], "parts": [{"text": turn["text"]}]})

    contents.append({"role": "user", "parts": [{"text": prompt}]})

    payload = {"contents": contents}
    headers = {"Content-Type": "application/json"}

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=25)
        if res.status_code == 200:
            data = res.json()
            candidates = data.get("candidates", [])
            if candidates:
                reply = candidates[0]["content"]["parts"][0]["text"]
                chat_history.append({"role": "user", "text": prompt})
                chat_history.append({"role": "model", "text": reply})
                return reply
        return f"Error en API Gemini (Status {res.status_code}): {res.text[:100]}"
    except Exception as e:
        return f"Error de conexión con Gemini: {str(e)}"


class CloudBlitzoHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def handle(self):
        try:
            super().handle()
        except Exception:
            pass

    def _send_json(self, data: Any, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        global pc_last_seen
        path = urllib.parse.urlparse(self.path).path

        if path == "/api/status" or path == "/":
            pc_online = (time.time() - pc_last_seen) < 120
            self._send_json({
                "status": "online",
                "mode": "cloud_24_7",
                "pc_status": "online" if pc_online else "offline",
                "bot_name": "Blitzo Cloud Core",
                "user": USER_NAME,
                "server_time": time.strftime("%Y-%m-%d %H:%M:%S")
            })

        elif path == "/api/mobile/pending_replies":
            if pending_mobile_replies:
                rep = pending_mobile_replies.pop(0)
                self._send_json({"has_reply": True, "data": rep})
            else:
                self._send_json({"has_reply": False})

        elif path == "/api/pc/pending_commands":
            # Llamado por la PC al encenderse para recoger tareas diferidas
            cmds = list(pending_pc_commands)
            pending_pc_commands.clear()
            self._send_json({"commands": cmds})

        else:
            self._send_json({"error": "Ruta no encontrada"}, status=404)

    def do_POST(self):
        global pc_last_seen
        path = urllib.parse.urlparse(self.path).path
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"

        try:
            req_data = json.loads(body)
        except Exception:
            req_data = {}

        if path == "/api/chat":
            msg = req_data.get("message", "")
            system_prompt = (
                f"Sos Blitzo, un compañero y asistente personal inteligente para {USER_NAME}. "
                f"Estás corriendo 24/7 en el servidor Cloud. Hablás con tono directo, coloquial, inteligente, con humor sutil "
                f"y total lealtad a {USER_NAME}. Respondé de forma ágil y natural."
            )
            reply = call_gemini(msg, system_prompt=system_prompt)
            self._send_json({"reply": reply})

        elif path == "/api/mobile/incoming":
            # Triage de WhatsApp en la nube 24/7
            sender = req_data.get("sender", "Contacto")
            text = req_data.get("text", "")
            notif_id = req_data.get("id", str(time.time()))

            prompt = (
                f"Actuá como {USER_NAME} respondiendo un WhatsApp.\n"
                f"De: {sender}\nMensaje: \"{text}\"\n"
                f"Generá 1 sola frase corta, natural y con confianza de cómo respondería {USER_NAME}."
            )
            draft = call_gemini(prompt).strip().strip('"')
            self._send_json({"status": "received", "suggested_reply": draft})

        elif path == "/api/pc/heartbeat":
            # La PC reporta que está viva
            pc_last_seen = time.time()
            self._send_json({"status": "alive", "time": time.time()})

        elif path == "/api/pc/queue_command":
            # Encolar orden para cuando la PC se prenda
            cmd = req_data.get("command", "")
            pending_pc_commands.append({"command": cmd, "queued_at": time.time()})
            self._send_json({"success": True, "message": "Comando encolado para la PC"})

        else:
            self._send_json({"error": "Endpoint no válido"}, status=404)


def run_cloud_server():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), CloudBlitzoHandler)
    print(f"⚡ [Blitzo Cloud Hub 24/7 activo en puerto {PORT}]")
    server.serve_forever()


if __name__ == "__main__":
    run_cloud_server()
