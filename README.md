# Polla DCC Bot 🏆

Este es un bot de Telegram diseñado para monitorear resultados de fútbol en vivo desde la API de ESPN y enviar notificaciones automáticas al grupo sobre goles, medio tiempo y finalizaciones de los partidos. Además, permite consultar la cartelera actual con el comando `/partidos` y obtener información con `/info`.

## Requisitos Previos

Antes de desplegar el bot en tu servidor, necesitas asegurarte de tener configurado tu archivo de variables de entorno. Crea un archivo `.env` en la misma carpeta del proyecto con las siguientes credenciales:

```env
TELEGRAM_TOKEN = "TOKEN DEL BOT DE TELEGRAM"
CHAT_ID = "CHAT ID (INCLUYE EL -)"
ESPN_URL = "URL_DE_LA_API_DE_ESPN"
```

## Tutorial de Despliegue en Servidor

Sigue estos pasos para instalar y ejecutar el bot en tu servidor Linux de forma permanente.

### 1. Clonar el repositorio y acceder a la carpeta
```bash
git clone <URL_DEL_REPOSITORIO>
cd POLLADCC
```

### 2. Instalar las Dependencias
Asegúrate de tener `pip` instalado. Luego, instala las librerías necesarias ejecutando:
```bash
pip3 install -r requirements.txt
```

### 3. Ejecución Permanente (Background) 🚀

Para que el bot se mantenga encendido 24/7 incluso después de cerrar tu conexión SSH al servidor, debes ejecutarlo en segundo plano usando la herramienta `nohup`.

Ejecuta el siguiente comando en la consola:
```bash
nohup python3 bot.py > salida.txt 2>&1 &
```
*¡Listo! El bot ahora está corriendo silenciosamente en el fondo. Todos los errores y registros de sistema se guardarán en `salida.txt` y los registros propios del bot en `bot.log`.*

---

## Administración Básica del Bot

### Cómo apagar el Bot 🛑

Dado que el bot se está ejecutando en segundo plano, presionar `Ctrl + C` en tu terminal no lo detendrá. Para apagarlo de forma segura, simplemente usa el siguiente comando para matar el proceso de Python asociado:

```bash
pkill -f bot.py
```
*(Si por alguna razón esto no funciona, puedes buscar el ID del proceso exacto con `ps aux | grep bot.py` y luego usar `kill <PID>`)*.

### Monitoreo en Tiempo Real 🔎

Como el bot corre en segundo plano (`nohup`) y ya no imprime texto directamente en tu pantalla, puedes "asomarte" a sus logs para ver qué está haciendo en vivo y en directo (como las alertas de goles que envía o consultas a la API).

Para ver los registros del bot en tiempo real:
```bash
tail -f bot.log
```

Para ver posibles errores críticos que el sistema operativo arroje:
```bash
tail -f salida.txt
```

Para salir del modo de visualización de logs, simplemente presiona `Ctrl + C`. **Ojo:** Esto solo cerrará el visor de texto de tu pantalla, tu bot seguirá ejecutándose felizmente en segundo plano.
