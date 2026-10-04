import os
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetParticipantRequest

# === 1. ВЕБ-СЕРВЕР ДЛЯ ОБХОДА ПРОВЕРКИ ПОРТОВ RENDER ===
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Gatekeeper Userbot is running!")

    def log_message(self, format, *args):
        return

def run_health_check_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

threading.Thread(target=run_health_check_server, daemon=True).start()

# === 2. ДАННЫЕ И НАСТРОЙКИ АВТОРИЗАЦИИ ===
API_ID = int(os.environ.get("API_ID", 28155925))
API_HASH = os.environ.get("API_HASH", "13cf6bb2641bfb7e67548650d65d9e7e")
SESSION_STRING = os.environ.get("SESSION_STRING")

REQUIRED_CHANNELS = ["skuprat", "RatLolz"]

# Инициализация с использованием StringSession
client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

async def is_subscribed_to_all(user_id):
    """Проверяет подписку пользователя на все каналы."""
    for channel in REQUIRED_CHANNELS:
        try:
            await client(GetParticipantRequest(
                channel=channel,
                participant=user_id
            ))
        except Exception:
            return False
    return True

@client.on(events.NewMessage(incoming=True))
async def check_private_messages(event):
    if not event.is_private:
        return

    sender = await event.get_sender()
    if not sender or getattr(sender, 'bot', False) or getattr(sender, 'is_self', False):
        return

    user_id = event.sender_id

    if not await is_subscribed_to_all(user_id):
        print(f"🚫 Сообщение от {user_id} удалено (нет подписки).")

        # Удаляем входящее сообщение
        try:
            await event.delete(revoke=True)
        except Exception as e:
            print(f"Ошибка при удалении: {e}")

        # HTML-разметка: <b> — жирный текст, <blockquote> — цитата
        full_text = (
            "👋 <b>Ку что бы писать мне</b>\n"
            "<b>подпишись на каналы</b>\n"
            "<blockquote><b>Канал @skuprat</b>\n"
            "<b>Канал @RatLolz</b></blockquote>"
        )

        try:
            await client.send_message(
                user_id,
                full_text,
                parse_mode='html',
                link_preview=False
            )
        except Exception as e:
            print(f"Ошибка при отправке: {e}")

async def main():
    print("🚀 Юзербот-фильтр ЛС запущен!")
    await client.start()
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
