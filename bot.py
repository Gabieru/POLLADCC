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
        self.ultimos_resultados_tarjetas = []
        self.ultima_consulta_api = 0
        self.ultimo_comando_partidos = 0
        self.ultimo_comando_tarjetas = 0
        self.lock = threading.Lock()
        self.is_paused = False
        self.avisos_10m = set()
        self.partidos_terminados = {}
        self.partidos_en_penales = set()
        
        try:
            import json
            with open("fifa_flags.json", "r") as f:
                self.flags = json.load(f)
        except Exception as e:
            logging.error(f"Error cargando banderas: {e}")
            self.flags = {}

    def get_flag(self, abbreviation):
        return self.flags.get(abbreviation, "🏳️")

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
            "away_score": int(away_team.get("score", 0)),
            "home_shootout": int(home_team.get("shootoutScore", 0)),
            "away_shootout": int(away_team.get("shootoutScore", 0))
        }

    def _obtener_eventos(self, match_id, home_id, away_id, home_abbr, away_abbr):
        try:
            url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/summary?event={match_id}"
            r = requests.get(url, timeout=5)
            data = r.json()
            home_scorers = []
            away_scorers = []
            home_cards = []
            away_cards = []
            
            if "keyEvents" in data:
                for event in data["keyEvents"]:
                    short_text = event.get("shortText", "")
                    team_id = str(event.get("team", {}).get("id", ""))
                    clock = event.get("clock", {}).get("displayValue", "")
                    participants = event.get("participants", [])
                    players = [p.get("athlete", {}).get("displayName", "") for p in participants]
                    jugador = players[0] if players else "Jugador"
                    
                    # Formatear a Inicial. Apellido (ej: R. Schmid)
                    partes = jugador.split()
                    if len(partes) >= 2:
                        jugador = f"{partes[0][0]}. {' '.join(partes[1:])}"
                    
                    texto_evento = f"{jugador} {clock}"
                    
                    if "Goal" in short_text or "Penalty - Score" in short_text or "Own Goal" in short_text:
                        if team_id == home_id:
                            home_scorers.append(texto_evento)
                        elif team_id == away_id:
                            away_scorers.append(texto_evento)
                    elif "Yellow Card" in short_text:
                        texto_evento = f"🟨 {texto_evento}"
                        if team_id == home_id:
                            home_cards.append(texto_evento)
                        elif team_id == away_id:
                            away_cards.append(texto_evento)
                    elif "Red Card" in short_text:
                        texto_evento = f"🟥 {texto_evento}"
                        if team_id == home_id:
                            home_cards.append(texto_evento)
                        elif team_id == away_id:
                            away_cards.append(texto_evento)
            
            eventos_formateados_goles = ""
            if home_scorers:
                eventos_formateados_goles += f"\n   {home_abbr}: ⚽ " + ", ".join(home_scorers)
            if away_scorers:
                eventos_formateados_goles += f"\n   {away_abbr}: ⚽ " + ", ".join(away_scorers)

            eventos_formateados_tarjetas = ""
            if home_cards:
                eventos_formateados_tarjetas += f"\n   {home_abbr}: " + ", ".join(home_cards)
            if away_cards:
                eventos_formateados_tarjetas += f"\n   {away_abbr}: " + ", ".join(away_cards)
                
            return eventos_formateados_goles, eventos_formateados_tarjetas, home_scorers, away_scorers, home_cards, away_cards
        except Exception as e:
            logging.error(f"Error obteniendo eventos del partido {match_id}: {e}")
            return "", "", [], [], [], []

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
        if self.is_paused:
            return

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

        if (home_score < previous_state["home_score"]) or (away_score < previous_state["away_score"]):
            if home_score < previous_state["home_score"]:
                equipo_afectado = info["home_name"]
                bandera_afectado = info["home_flag"]
            else:
                equipo_afectado = info["away_name"]
                bandera_afectado = info["away_flag"]

            self.enviar_mensaje(
                f"❌ <b>¡Gol Anulado!</b>\n"
                f"Se ha invalidado el gol de {bandera_afectado} {equipo_afectado}.\n"
                f"Marcador actualizado:\n{home} {home_score} - {away_score} {away}"
            )

        if status_state == "in" and previous_state["status_state"] == "pre":
            self.enviar_mensaje(f"🟢 <b>¡Comienza el partido!</b>\n{home} {home_score} - {away_score} {away}")

        if status_name == "STATUS_HALFTIME" and previous_state["status_name"] != "STATUS_HALFTIME":
            self.enviar_mensaje(f"⏳ <b>¡Medio Tiempo!</b>\n{home} {home_score} - {away_score} {away}")

        if status_state == "post" and previous_state["status_state"] != "post":
            self.enviar_mensaje(f"🔴 <b>¡Terminó el partido!</b>\n{home} {home_score} - {away_score} {away}")

        # Check cards
        home_cards = current_state.get("home_cards", [])
        away_cards = current_state.get("away_cards", [])
        prev_home_cards = previous_state.get("home_cards", [])
        prev_away_cards = previous_state.get("away_cards", [])
        
        for card in home_cards:
            if card not in prev_home_cards:
                tipo = "Tarjeta Roja" if "🟥" in card else "Tarjeta Amarilla"
                self.enviar_mensaje(f"{card[0]} <b>¡{tipo} para {info['home_name']}!</b>\n👤 Jugador: {card[2:]}\n⏱️ {status['clock']}")
                
        for card in away_cards:
            if card not in prev_away_cards:
                tipo = "Tarjeta Roja" if "🟥" in card else "Tarjeta Amarilla"
                self.enviar_mensaje(f"{card[0]} <b>¡{tipo} para {info['away_name']}!</b>\n👤 Jugador: {card[2:]}\n⏱️ {status['clock']}")

    def procesar_partidos(self):
        with self.lock:
            partidos_actuales = self.obtener_partidos()
            resultados_texto = []
            resultados_tarjetas = []

            for evento in partidos_actuales:
                match_id = evento.get("id")
                
                info = self._extract_team_info(evento)
                if not info:
                    continue
                
                status = self._format_match_status(evento)
                
                # 10 minute warning
                if status["status_state"] == "pre":
                    date_str = evento.get("date", "")
                    if date_str and match_id not in self.avisos_10m:
                        try:
                            utc_dt = datetime.strptime(date_str.replace("Z", "+0000"), "%Y-%m-%dT%H:%M%z")
                            diferencia = (utc_dt.timestamp() - time.time()) / 60.0
                            if 9 <= diferencia <= 11:
                                self.enviar_mensaje(f"⏰ <b>¡Recuerden hacer sus predicciones para {info['home_name']} vs {info['away_name']}!</b>\n¡Estamos a 10 minutos de partir!")
                                self.avisos_10m.add(match_id)
                        except Exception as e:
                            pass
                
                home_score = info["home_score"]
                away_score = info["away_score"]
                home_shootout = info["home_shootout"]
                away_shootout = info["away_shootout"]
                status_state = status["status_state"]
                status_name = status["status_name"]

                if "SHOOTOUT" in status_name or "PENALT" in status_name:
                    if match_id not in self.partidos_en_penales:
                        self.partidos_en_penales.add(match_id)
                        self.enviar_mensaje(f"😱 <b>¡El partido se va a penales!</b>\n{info['home_str']} vs {info['away_str']}\nLas actualizaciones automáticas se pausarán para evitar spoilers.")

                if status_state == "post" and match_id not in self.partidos_terminados:
                    self.partidos_terminados[match_id] = time.time()

                marcador_home = str(home_score)
                marcador_away = str(away_score)
                if home_shootout > 0 or away_shootout > 0 or match_id in self.partidos_en_penales:
                    marcador_home = f"({home_shootout}) {home_score}"
                    marcador_away = f"{away_score} ({away_shootout})"

                linea_resultado = f"{status['estado_formateado']}\n{info['home_str']} <b>{marcador_home} - {marcador_away}</b> {info['away_str']}"

                home_scorers = []
                away_scorers = []
                home_cards = []
                away_cards = []
                eventos_goles = ""
                eventos_tarjetas = ""
                if status_state == "in" or status_name == "STATUS_HALFTIME" or status_state == "post":
                    eventos_goles, eventos_tarjetas, home_scorers, away_scorers, home_cards, away_cards = self._obtener_eventos(
                        match_id, info["home_id"], info["away_id"], info["home_flag"], info["away_flag"]
                    )
                    linea_resultado += eventos_goles

                linea_resultado_tarjeta = f"{status['estado_formateado']}\n{info['home_str']} <b>{marcador_home} - {marcador_away}</b> {info['away_str']}" + eventos_tarjetas
                resultados_texto.append(linea_resultado)
                resultados_tarjetas.append(linea_resultado_tarjeta)

                current_state = {
                    "home_score": home_score,
                    "away_score": away_score,
                    "status_state": status_state,
                    "status_name": status_name,
                    "home_scorers": home_scorers,
                    "away_scorers": away_scorers,
                    "home_cards": home_cards,
                    "away_cards": away_cards
                }

                if match_id not in self.match_states:
                    if status_state == "in": 
                        self.enviar_mensaje(f"🟢 <b>¡Partido en curso!</b> ({status['clock']})\n{info['home_str']} {home_score} - {away_score} {info['away_str']}")
                    self.match_states[match_id] = current_state
                    continue

                previous_state = self.match_states[match_id]
                
                if match_id in self.partidos_en_penales:
                    if status_state == "post":
                        tiempo_fin = self.partidos_terminados.get(match_id, time.time())
                        if time.time() - tiempo_fin < 120:
                            current_state["status_state"] = previous_state["status_state"]
                            self.match_states[match_id] = current_state
                            continue
                        else:
                            if previous_state["status_state"] != "post":
                                self.enviar_mensaje(f"🔴 <b>¡Terminó el partido tras los penales!</b>\n{info['home_str']} <b>{marcador_home} - {marcador_away}</b> {info['away_str']}")
                            self.match_states[match_id] = current_state
                            continue
                    else:
                        self.match_states[match_id] = current_state
                        continue

                self._process_match_alerts(match_id, info, status, current_state, previous_state)
                self.match_states[match_id] = current_state
            
            self.ultimos_resultados_texto = resultados_texto
            self.ultimos_resultados_tarjetas = resultados_tarjetas
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
        "⚽ /partidos - Muestra el marcador actual de la cartelera de partidos y sus respectivos goleadores.\n"
        "🟨 /tarjetas - Muestra el registro de tarjetas del día de hoy.\n"
        "⏸️ /pausar - Pausa o reanuda las notificaciones (solo administradores).\n\n"
        "<i>Nota: El comando solo esta disponible en grupos y posee una enfriación.</i>"
    )
    bot.reply_to(message, texto, parse_mode="HTML")

@bot.message_handler(commands=['pausar'])
def comando_pausar(message):
    if message.chat.type not in ['group', 'supergroup']:
        bot.reply_to(message, "⚠️ Lo siento, solo puedo responder comandos dentro de un grupo.")
        return

    miembro = bot.get_chat_member(message.chat.id, message.from_user.id)
    if miembro.status not in ['administrator', 'creator']:
        bot.reply_to(message, "❌ Solo los administradores del grupo pueden usar este comando.")
        return

    world_cup_bot.is_paused = not world_cup_bot.is_paused
    estado = "pausado" if world_cup_bot.is_paused else "reanudado"
    bot.reply_to(message, f"✅ Las actualizaciones automáticas se han <b>{estado}</b>.", parse_mode="HTML")

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

@bot.message_handler(commands=['tarjetas'])
def comando_tarjetas(message):
    if message.chat.type not in ['group', 'supergroup']:
        bot.reply_to(message, "⚠️ Lo siento, solo puedo responder comandos dentro de un grupo.")
        return

    ahora = time.time()
    tiempo_pasado = ahora - world_cup_bot.ultimo_comando_tarjetas
    if tiempo_pasado < 60:
        tiempo_restante = int(60 - tiempo_pasado)
        bot.reply_to(message, f"⏳ Comando en enfriamiento. Por favor, espera {tiempo_restante} segundos.")
        return

    world_cup_bot.ultimo_comando_tarjetas = ahora
    
    if not world_cup_bot.ultimos_resultados_tarjetas:
        bot.reply_to(message, "Aún no hay datos de partidos disponibles. Intenta en un momento.")
        return
        
    cantidad = len(world_cup_bot.ultimos_resultados_tarjetas)
    texto_respuesta = f"🟨 <b>Tarjetas de los Partidos (últimos {cantidad} partidos):</b>\n\n" + "\n\n".join(world_cup_bot.ultimos_resultados_tarjetas)
    bot.send_message(message.chat.id, texto_respuesta, parse_mode="HTML")

if __name__ == "__main__":
    hilo_polling = threading.Thread(target=world_cup_bot.polling_thread, kwargs={'intervalo_segundos': 60})
    hilo_polling.daemon = True
    hilo_polling.start()

    logging.info("Iniciando escucha de comandos en Telegram...")
    bot.infinity_polling()