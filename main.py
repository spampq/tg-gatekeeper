import os
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# === 1. ВЕБ-СЕРВЕР ДЛЯ РАБОТЫ НА RENDER ===
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Userbot is running!")

    def log_message(self, format, *args):
        return

def run_health_check_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

# Запускаем веб-сервер в фоновом потоке
threading.Thread(target=run_health_check_server, daemon=True).start()

# === 2. НАСТРОЙКИ ЮЗЕРБОТА ===
API_ID = int(os.environ.get("API_ID", 28155925))
API_HASH = os.environ.get("API_HASH", "13cf6bb2641bfb7e67548650d65d9e7e")
SESSION_STRING = os.environ.get("SESSION_STRING", "")

REQUIRED_CHANNELS = ["@skuprat", "@RatLolz"]

def main():
    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

    async def check_subscription(user_id):
        for channel in REQUIRED_CHANNELS:
            try:
                participant = await client.get_permissions(channel, user_id)
                if not participant:
                    return False
            except Exception:
                return False
        return True

    @client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
    async def private_message_handler(event):
        sender = await event.get_sender()
        if not sender or sender.bot or sender.id == (await client.get_me()).id:
            return

        is_subscribed = await check_subscription(sender.id)
        if not is_subscribed:
            try:
                await event.delete()
            except Exception:
                pass

            channels_text = ", ".join(REQUIRED_CHANNELS)
            warning_text = (
                f"❌ **Доступ ограничен!**\n\nЧтобы написать мне, подпишитесь на "
                f"каналы: {channels_text}\nПосле подписки отправьте сообщение заново."
            )
            await event.respond(warning_text)

    with client:
        print("🚀 Gatekeeper is running successfully!")
        client.run_until_disconnected()

if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as e:
            print(f"⚠️ Ошибка соединения: {e}. Перезапуск через 5 секунд...")
            time.sleep(5)
