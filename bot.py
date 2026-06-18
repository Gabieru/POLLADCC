import time
import requests
import os
import logging
import threading
import telebot
import random
from datetime import datetime
from zoneinfo import ZoneInfo
import sys
from dotenv import load_dotenv

env_file = sys.argv[1] if len(sys.argv) > 1 else ".env"
load_dotenv(env_file)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
ESPN_URL = os.getenv("ESPN_URL")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

class WorldCupBot:
    def __init__(self):
        self.match_states = {}
        self.ultimos_resultados_texto = []
        self.ultima_consulta_api = 0
        self.ultimo_comando_partidos = 0
        self.lock = threading.Lock()

    def get_flag(self, abbreviation):
        flags = {
            "COL": "🇨🇴", "UZB": "🇺🇿", "ARG": "🇦🇷", "BRA": "🇧🇷", "MEX": "🇲🇽", 
            "USA": "🇺🇸", "ESP": "🇪🇸", "FRA": "🇫🇷", "GER": "🇩🇪", "ENG": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
            "ITA": "🇮🇹", "POR": "🇵🇹", "URU": "🇺🇾", "ECU": "🇪🇨", "CHI": "🇨🇱",
            "PER": "🇵🇪", "VEN": "🇻🇪", "PAR": "🇵🇾", "BOL": "🇧🇴", "AUT": "🇦🇹",
            "NED": "🇳🇱", "BEL": "🇧🇪", "CRO": "🇭🇷", "JPN": "🇯🇵", "KOR": "🇰🇷",
            "MAR": "🇲🇦", "SEN": "🇸🇳", "CAN": "🇨🇦", "CRC": "🇨🇷", "KSA": "🇸🇦",
            "AUS": "🇦🇺", "TUN": "🇹🇳", "QAT": "🇶🇦", "WAL": "🏴󠁧󠁢󠁷󠁬󠁳󠁿", "POL": "🇵🇱",
            "SRB": "🇷🇸", "SUI": "🇨🇭", "CMR": "🇨🇲", "GHA": "🇬🇭", "IRN": "🇮🇷"
        }
        return flags.get(abbreviation, "🏳️")

    def enviar_mensaje(self, texto):
        try:
            bot.send_message(CHAT_ID, texto, parse_mode="HTML")
            logging.info(f"Mensaje enviado a Telegram: {texto[:30]}...")
        except Exception as e:
            logging.error(f"Error enviando mensaje a Telegram: {e}")

    def obtener_partidos(self):
        try:
            response = requests.get(ESPN_URL)
            data = response.json()
            eventos = data.get("events", [])
            logging.info(f"API ESPN consultada. {len(eventos) if eventos else 0} partidos obtenidos.")
            self.ultima_consulta_api = time.time()
            return eventos
        except Exception as e:
            logging.error(f"Error consultando la API: {e}")
            return []

    def _extract_team_info(self, evento):
        competitions = evento.get("competitions", [{}])
        competitors = competitions[0].get("competitors", [])
        
        if len(competitors) < 2:
            return None
        
        home_team = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
        away_team = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])
        
        home_name = home_team.get("team", {}).get("displayName", "Local")
        away_name = away_team.get("team", {}).get("displayName", "Visitante")

        home_abbr = home_team.get("team", {}).get("abbreviation", home_name[:3].upper())
        away_abbr = away_team.get("team", {}).get("abbreviation", away_name[:3].upper())
        
        home_flag = self.get_flag(home_abbr)
        away_flag = self.get_flag(away_abbr)
        
        return {
            "home_id": str(home_team.get("team", {}).get("id", "")),
            "away_id": str(away_team.get("team", {}).get("id", "")),
            "home_abbr": home_abbr,
            "away_abbr": away_abbr,
            "home_str": f"{home_flag} {home_name}",
            "away_str": f"{away_name} {away_flag}",
            "home_name": home_name,
            "away_name": away_name,
            "home_flag": home_flag,
            "away_flag": away_flag,
            "home_score": int(home_team.get("score", 0)),
            "away_score": int(away_team.get("score", 0))
        }

    def _obtener_goleadores(self, match_id, home_id, away_id, home_abbr, away_abbr):
        try:
            url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/summary?event={match_id}"
            r = requests.get(url, timeout=5)
            data = r.json()
            home_scorers = []
            away_scorers = []
            
            if "keyEvents" in data:
                for event in data["keyEvents"]:
                    short_text = event.get("shortText", "")
                    if "Goal" in short_text or "Penalty - Score" in short_text or "Own Goal" in short_text:
                        team_id = str(event.get("team", {}).get("id", ""))
                        clock = event.get("clock", {}).get("displayValue", "")
                        participants = event.get("participants", [])
                        players = [p.get("athlete", {}).get("displayName", "") for p in participants]
                        jugador = players[0] if players else "Jugador"
                        
                        # Formatear a Inicial. Apellido (ej: R. Schmid)
                        partes = jugador.split()
                        if len(partes) >= 2:
                            jugador = f"{partes[0][0]}. {' '.join(partes[1:])}"
                        
                        texto_gol = f"{jugador} {clock}"
                        
                        if team_id == home_id:
                            home_scorers.append(texto_gol)
                        elif team_id == away_id:
                            away_scorers.append(texto_gol)
            
            goles_formateados = ""
            if home_scorers:
                goles_formateados += f"\n   ⚽ {home_abbr}: {', '.join(home_scorers)}"
            if away_scorers:
                goles_formateados += f"\n   ⚽ {away_abbr}: {', '.join(away_scorers)}"
                
            return goles_formateados, home_scorers, away_scorers
        except Exception as e:
            logging.error(f"Error obteniendo goleadores del partido {match_id}: {e}")
            return "", [], []

    def _format_match_status(self, evento):
        status_obj = evento.get("status", {})
        status_state = status_obj.get("type", {}).get("state", "")
        status_name = status_obj.get("type", {}).get("name", "")
        clock = status_obj.get("displayClock", "")

        estado_formateado = f"🟢 ({clock})" if clock else ""
        if status_name == "STATUS_HALFTIME":
            estado_formateado = "⏳ (Medio Tiempo)"
        elif status_state == "post":
            estado_formateado = "🔴 (Finalizado)"
        elif status_state == "pre":
            date_str = evento.get("date", "")
            if date_str:
                try:
                    utc_dt = datetime.strptime(date_str.replace("Z", "+0000"), "%Y-%m-%dT%H:%M%z")
                    chile_dt = utc_dt.astimezone(ZoneInfo("America/Santiago"))
                    hora = chile_dt.strftime("%H:%M")
                    estado_formateado = f"🟡 (Hoy a las {hora})"
                except Exception:
                    estado_formateado = "🟡 (Por comenzar)"
            else:
                estado_formateado = "🟡 (Por comenzar)"

        return {
            "status_state": status_state,
            "status_name": status_name,
            "clock": clock,
            "estado_formateado": estado_formateado
        }

    def _process_match_alerts(self, match_id, info, status, current_state, previous_state):
        home_score = current_state["home_score"]
        away_score = current_state["away_score"]
        status_state = current_state["status_state"]
        status_name = current_state["status_name"]
        
        home = info["home_str"]
        away = info["away_str"]
        clock = status["clock"]

        if (home_score > previous_state["home_score"]) or (away_score > previous_state["away_score"]):
            if home_score > previous_state["home_score"]:
                equipo_anotador = info["home_name"]
                bandera_anotador = info["home_flag"]
            else:
                equipo_anotador = info["away_name"]
                bandera_anotador = info["away_flag"]

            toma_delantera = False
            if home_score > previous_state["home_score"] and home_score == away_score + 1 and previous_state["home_score"] == previous_state["away_score"]:
                toma_delantera = True
            elif away_score > previous_state["away_score"] and away_score == home_score + 1 and previous_state["home_score"] == previous_state["away_score"]:
                toma_delantera = True

            ultimo_goleador = ""
            if home_score > previous_state["home_score"] and current_state.get("home_scorers"):
                ultimo_goleador = current_state["home_scorers"][-1]
            elif away_score > previous_state["away_score"] and current_state.get("away_scorers"):
                ultimo_goleador = current_state["away_scorers"][-1]

            if toma_delantera:
                mensaje_gol = f"🔥 <b>¡{bandera_anotador} {equipo_anotador} toma la delantera con un golazo!!!</b>"
            else:
                opciones = [
                    f"⚽ <b>¡Gooooool de {bandera_anotador} {equipo_anotador}!</b>",
                    f"🚀 <b>¡Golazo de {bandera_anotador} {equipo_anotador}!</b>",
                    f"🥅 <b>¡Grito de gol para {bandera_anotador} {equipo_anotador}!</b>"
                ]
                mensaje_gol = random.choice(opciones)
            
            if ultimo_goleador:
                mensaje_gol += f"\n👤 Anotado por: <b>{ultimo_goleador}</b>"

            self.enviar_mensaje(
                f"{mensaje_gol}\n"
                f"⏱️ {clock}\n"
                f"{home} {home_score} - {away_score} {away}"
            )

        if status_name == "STATUS_HALFTIME" and previous_state["status_name"] != "STATUS_HALFTIME":
            self.enviar_mensaje(f"⏳ <b>¡Medio Tiempo!</b>\n{home} {home_score} - {away_score} {away}")

        if status_state == "post" and previous_state["status_state"] != "post":
            self.enviar_mensaje(f"🔴 <b>¡Terminó el partido!</b>\n{home} {home_score} - {away_score} {away}")

    def procesar_partidos(self):
        with self.lock:
            partidos_actuales = self.obtener_partidos()
            resultados_texto = []

            for evento in partidos_actuales:
                match_id = evento.get("id")
                
                info = self._extract_team_info(evento)
                if not info:
                    continue
                
                status = self._format_match_status(evento)
                
                home_score = info["home_score"]
                away_score = info["away_score"]
                status_state = status["status_state"]
                status_name = status["status_name"]

                linea_resultado = f"{status['estado_formateado']}\n{info['home_str']} <b>{home_score} - {away_score}</b> {info['away_str']}"

                home_scorers = []
                away_scorers = []
                if status_state == "in" or status_name == "STATUS_HALFTIME" or status_state == "post":
                    goles_formateados, home_scorers, away_scorers = self._obtener_goleadores(
                        match_id, info["home_id"], info["away_id"], info["home_flag"], info["away_flag"]
                    )
                    linea_resultado += goles_formateados

                resultados_texto.append(linea_resultado)

                current_state = {
                    "home_score": home_score,
                    "away_score": away_score,
                    "status_state": status_state,
                    "status_name": status_name,
                    "home_scorers": home_scorers,
                    "away_scorers": away_scorers
                }

                if match_id not in self.match_states:
                    if status_state == "in": 
                        self.enviar_mensaje(f"🟢 <b>¡Partido en curso!</b> ({status['clock']})\n{info['home_str']} {home_score} - {away_score} {info['away_str']}")
                    self.match_states[match_id] = current_state
                    continue

                previous_state = self.match_states[match_id]
                self._process_match_alerts(match_id, info, status, current_state, previous_state)
                self.match_states[match_id] = current_state
            
            self.ultimos_resultados_texto = resultados_texto
            return resultados_texto

    def polling_thread(self, intervalo_segundos=60):
        logging.info("Iniciando hilo de monitoreo de partidos...")
        while True:
            ahora = time.time()
            if ahora - self.ultima_consulta_api >= intervalo_segundos:
                self.procesar_partidos()
            
            time.sleep(5)

world_cup_bot = WorldCupBot()

@bot.message_handler(commands=['info', 'start', 'ayuda', 'help'])
def comando_info(message):
    texto = (
        "🤖 <b>¡Hola! Soy DCCin versión Polla Mundialera v2.</b>\n\n"
        "<b>¿Qué hago?</b>\n"
        "Me encargo de monitorear todos los partidos. ¡Si algo cambia, seré el primero en notificarlo!\n\n"
        "<b>Comandos disponibles:</b>\n"
        "⚽ /partidos - Muestra el marcador actual de la cartelera de partidos y sus respectivos goleadores.\n\n"
        "<i>Nota: El comando solo esta disponible en grupos y posee una enfriación.</i>"
    )
    bot.reply_to(message, texto, parse_mode="HTML")

@bot.message_handler(commands=['partidos'])
def comando_partidos(message):
    if message.chat.type not in ['group', 'supergroup']:
        bot.reply_to(message, "⚠️ Lo siento, solo puedo responder comandos dentro de un grupo.")
        return

    ahora = time.time()
    tiempo_pasado = ahora - world_cup_bot.ultimo_comando_partidos
    if tiempo_pasado < 60:
        tiempo_restante = int(60 - tiempo_pasado)
        bot.reply_to(message, f"⏳ Comando en enfriamiento. Por favor, espera {tiempo_restante} segundos.")
        return

    world_cup_bot.ultimo_comando_partidos = ahora
    
    if not world_cup_bot.ultimos_resultados_texto:
        bot.reply_to(message, "Aún no hay datos de partidos disponibles. Intenta en un momento.")
        return
        
    cantidad = len(world_cup_bot.ultimos_resultados_texto)
    texto_respuesta = f"📋 <b>Estado de los Partidos (últimos {cantidad} partidos):</b>\n\n" + "\n\n".join(world_cup_bot.ultimos_resultados_texto)
    bot.send_message(message.chat.id, texto_respuesta, parse_mode="HTML")

if __name__ == "__main__":
    hilo_polling = threading.Thread(target=world_cup_bot.polling_thread, kwargs={'intervalo_segundos': 60})
    hilo_polling.daemon = True
    hilo_polling.start()

    logging.info("Iniciando escucha de comandos en Telegram...")
    bot.infinity_polling()