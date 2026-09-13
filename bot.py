import logging
import asyncio
import html
import tempfile
import psutil
import os
import io
import json
import glob
import subprocess
import sys
import webbrowser
import urllib.request
import win32com.client
from datetime import datetime
from PIL import ImageGrab
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
import config
from modules.file_manager import fm_handle, fm_handle_number, fm_send_listing

VK_MEDIA_PLAY_PAUSE = 0xB3
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1


def press_media_key(vk_code):
    pass


def set_volume(level):
    level = max(0, min(100, int(level)))
    try:
        from pycaw.pycaw import AudioUtilities
        devices = AudioUtilities.GetSpeakers()
        volume = devices.EndpointVolume
        volume.SetMasterVolumeLevelScalar(level / 100.0, None)
    except Exception:
        pass


def get_volume():
    try:
        from pycaw.pycaw import AudioUtilities
        devices = AudioUtilities.GetSpeakers()
        volume = devices.EndpointVolume
        return int(round(volume.GetMasterVolumeLevelScalar() * 100))
    except Exception:
        return 50


async def get_current_track():
    try:
        from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as SMTC

        mgr = await SMTC.request_async()
        session = mgr.get_current_session()
        if session:
            props = await session.try_get_media_properties_async()
            title = props.title or ""
            artist = props.artist or ""
            if artist and title:
                return f"{artist} - {title}"
            return title or None
    except Exception:
        pass
    return None


async def control_media(action):
    try:
        from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as SMTC

        mgr = await SMTC.request_async()
        session = mgr.get_current_session()
        if session:
            if action == "pause":
                await session.try_toggle_play_pause_async()
            elif action == "next":
                await session.try_skip_next_async()
            elif action == "prev":
                await session.try_skip_previous_async()
    except Exception:
        pass


def get_pc_info():
    info = {}
    try:
        ps = (
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
            "$os = Get-CimInstance Win32_OperatingSystem; "
            "$cpu = Get-CimInstance Win32_Processor; "
            "$gpu = Get-CimInstance Win32_VideoController; "
            "$ram = [math]::Round($os.TotalVisibleMemorySize/1MB, 1); "
            "$ram_free = [math]::Round($os.FreePhysicalMemory/1MB, 1); "
            "$disks = Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | "
            "ForEach-Object { \"$($_.DeviceID) $([math]::Round($_.Size/1GB,0))GB/$([math]::Round($_.FreeSpace/1GB,0))GB free\" }; "
            "Write-Output \"OS=$($os.Caption) $($os.Version)\"; "
            "Write-Output \"CPU=$($cpu.Name)\"; "
            "Write-Output \"CPU_CORES=$($cpu.NumberOfCores)/$($cpu.NumberOfLogicalProcessors)\"; "
            "Write-Output \"CPU_FREQ=$($cpu.MaxClockSpeed)MHz\"; "
            "Write-Output \"RAM=${ram}GB/$($ram_free)GB free\"; "
            "foreach ($g in $gpu) { Write-Output \"GPU=$($g.Name) $($g.AdapterRAM/1MB)MB\" }; "
            "foreach ($d in $disks) { Write-Output \"DISK=$d\" }"
        )
        r = subprocess.run(
            ["powershell", "-Command", ps],
            capture_output=True, text=True, timeout=10, encoding="utf-8",
        )
        for line in r.stdout.strip().split("\n"):
            if "=" in line:
                k, v = line.split("=", 1)
                info[k.strip()] = v.strip()
    except Exception:
        pass
    return info


def get_geo_info():
    try:
        req = urllib.request.Request(
            "https://ipinfo.io/json",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        parts = []
        if data.get("city"):
            parts.append(data["city"])
        if data.get("region"):
            parts.append(data["region"])
        if data.get("country"):
            parts.append(data["country"])
        loc = data.get("loc", "")
        return {
            "ip": data.get("ip", "?"),
            "location": ", ".join(parts) if parts else "?",
            "org": data.get("org", "?"),
            "coords": loc,
        }
    except Exception:
        return None


LOG_FILE = os.devnull
CONSOLE_FILE = os.devnull

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

PASSWORD = "2935auf45"
authorized_users = set()

USERS_FILE = "users.json"

_in_memory_users = {}

DESKTOP_DIRS = [
    os.path.join(os.path.expanduser("~"), "OneDrive", "\u0420\u0430\u0431\u043e\u0447\u0438\u0439 \u0441\u0442\u043e\u043b"),
    os.path.join(os.environ["PUBLIC"], "Desktop"),
    os.path.join(os.environ["USERPROFILE"], "Desktop"),
    os.path.join(os.environ["USERPROFILE"], "\u0420\u0430\u0431\u043e\u0447\u0438\u0439 \u0441\u0442\u043e\u043b"),
]

_program_cache = {}


def get_desktop():
    for d in DESKTOP_DIRS:
        if os.path.exists(d):
            return d
    return DESKTOP_DIRS[0]


def load_users():
    return _in_memory_users.copy()


def save_users(users):
    _in_memory_users.clear()
    _in_memory_users.update(users)


def update_user(user_id, username, first_name, action=None):
    users = load_users()
    uid = str(user_id)
    if uid not in users:
        users[uid] = {}
    users[uid]["username"] = username
    users[uid]["first_name"] = first_name
    if action:
        users[uid]["last_action"] = action
    save_users(users)


def is_banned(user_id):
    users = load_users()
    return users.get(str(user_id), {}).get("banned", False)


def log_event(user_id, username, first_name, action):
    now = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    entry = f"[{now}] ID:{user_id} | @{username} | {first_name} | {action}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(entry)


def get_logs(lines=30):
    if not os.path.exists(LOG_FILE):
        return "Логов пока нет."
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        all_lines = f.readlines()
    return "".join(all_lines[-lines:])


def pc_status():
    boot = psutil.boot_time()
    uptime_sec = psutil.time.time() - boot
    hours = int(uptime_sec // 3600)
    minutes = int((uptime_sec % 3600) // 60)
    cpu = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory().percent
    return f"🟢 ПК включён | Аптайм: {hours}ч {minutes}м | CPU: {cpu}% | RAM: {ram}%"


def get_desktop_programs():
    desktop = get_desktop()
    programs = []
    _program_cache.clear()
    for ext in ["*.lnk", "*.exe", "*.url"]:
        for f in glob.glob(os.path.join(desktop, ext)):
            name = os.path.splitext(os.path.basename(f))[0]
            if name not in _program_cache:
                _program_cache[name.lower()] = f
                programs.append(name)
    return sorted(set(programs))


def main_menu(context=None):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Скриншот", callback_data="screenshot")],
        [InlineKeyboardButton("Трансляция", callback_data="stream")],
        [InlineKeyboardButton("Инфо о ПК", callback_data="pc_info")],
        [InlineKeyboardButton("Управление ПК", callback_data="pc_control")],
        [InlineKeyboardButton("Запустить программу", callback_data="launch")],
        [InlineKeyboardButton("Убить процесс", callback_data="kill")],
        [InlineKeyboardButton("Файлы", callback_data="files")],
        [InlineKeyboardButton("Звук", callback_data="volume")],
        [InlineKeyboardButton("Картинка", callback_data="show_image")],
        [InlineKeyboardButton("Открыть сайт", callback_data="open_site")],
        [InlineKeyboardButton("Музыка", callback_data="music")],
        [InlineKeyboardButton("Ошибка", callback_data="error_popup")],
    ])


def back_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="back")]])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uname = user.username or "нет"
    log_event(user.id, uname, user.first_name, "нажал /start")
    update_user(user.id, uname, user.first_name, "нажал /start")

    if is_banned(user.id):
        await update.message.reply_text("Вы забанены. Доступ запрещён.")
        return

    context.user_data["authorized"] = user.id in authorized_users

    if context.user_data["authorized"]:
        await update.message.reply_text(
            f"{pc_status()}\n\nВыбери действие:", reply_markup=main_menu(), parse_mode="HTML",
        )
    else:
        await update.message.reply_text(f"{pc_status()}\n\nВведи пароль:")
        context.user_data["waiting_for_password"] = True


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.error("Exception while handling an update:", exc_info=context.error)
    try:
        if update and hasattr(update, "effective_chat") and update.effective_chat:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Произошла ошибка. Попробуй ещё раз.",
            )
    except Exception:
        pass


async def check_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uname = user.username or "нет"
    text = update.message.text.strip()

    if is_banned(user.id):
        await update.message.reply_text("Вы забанены. Доступ запрещён.")
        return

    if text == PASSWORD:
        authorized_users.add(user.id)
        users = load_users()
        uid = str(user.id)
        if uid not in users:
            users[uid] = {}
        users[uid]["authorized"] = True
        save_users(users)
        log_event(user.id, uname, user.first_name, "вошёл в бота (пароль верный)")
        update_user(user.id, uname, user.first_name, "вошёл в бота")
        context.user_data["authorized"] = True
        context.user_data.pop("waiting_for_password", None)
        await update.message.reply_text(
            f"Доступ разрешён!\n\n{pc_status()}\n\nВыбери действие:",
            reply_markup=main_menu(), parse_mode="HTML",
        )
    else:
        log_event(user.id, uname, user.first_name, f"ввёл неверный пароль: {text}")
        update_user(user.id, uname, user.first_name, "ввёл неверный пароль")
        await update.message.reply_text("Неверный пароль. Попробуй ещё:")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    if not context.user_data.get("authorized"):
        await query.answer("Сначала введи пароль через /start", show_alert=True)
        return
    uname = user.username or "нет"
    log_event(user.id, uname, user.first_name, f"нажал кнопку: {query.data}")
    update_user(user.id, uname, user.first_name, f"нажал кнопку: {query.data}")
    if not query.data.startswith("fm:"):
        await query.answer()

    if query.data == "back":
        context.user_data.pop("_fm_mode", None)
        context.user_data.pop("_fm_active", None)
        await query.edit_message_text(
            f"{pc_status()}\n\nВыбери действие:", reply_markup=main_menu(), parse_mode="HTML",
        )

    elif query.data == "screenshot":
        if not context.user_data.get("screenshot_enabled", True):
            await query.answer("Ошибка: скриншот временно недоступен", show_alert=True)
            return
        await query.edit_message_text("Делаю скриншот...")
        try:
            img = ImageGrab.grab()
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            await query.message.reply_photo(photo=InputFile(buf), caption="Скриншот экрана")
            await query.message.edit_text(
                f"{pc_status()}\n\nВыбери действие:", reply_markup=main_menu(), parse_mode="HTML",
            )
        except Exception as e:
            await query.message.edit_text(
                f"Ошибка скриншота: {e}", reply_markup=back_button(),
            )

    elif query.data == "monitor":
        cpu = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage("C:\\")
        boot = psutil.boot_time()
        uptime_sec = psutil.time.time() - boot
        hours = int(uptime_sec // 3600)
        minutes = int((uptime_sec % 3600) // 60)

        text = (
            f"<b>Мониторинг ПК</b>\n\n"
            f"Аптайм: {hours}ч {minutes}м\n"
            f"CPU: {cpu}%\n"
            f"RAM: {ram.percent}% ({ram.used // (1024**3)}ГБ / {ram.total // (1024**3)}ГБ)\n"
            f"Диск C: {disk.percent}% ({disk.used // (1024**3)}ГБ / {disk.total // (1024**3)}ГБ)\n"
            f"CPU temp: {get_cpu_temp()}"
        )
        await query.edit_message_text(text, reply_markup=back_button(), parse_mode="HTML")

    elif query.data == "pc_info":
        await query.edit_message_text("⏳ Собираю инфу о ПК...")
        info, geo = await asyncio.to_thread(lambda: (get_pc_info(), get_geo_info()))
        text = "<b>Информация о ПК:</b>\n\n"
        if "OS" in info:
            text += f"ОС: {info['OS']}\n"
        if "CPU" in info:
            text += f"CPU: {info['CPU']}\n"
        if "CPU_CORES" in info:
            text += f"Ядра/Потоки: {info['CPU_CORES']}\n"
        if "CPU_FREQ" in info:
            text += f"Частота: {info['CPU_FREQ']}\n"
        if "RAM" in info:
            text += f"RAM: {info['RAM']}\n"
        for k, v in info.items():
            if k.startswith("GPU"):
                text += f"GPU: {v}\n"
        for k, v in info.items():
            if k.startswith("DISK"):
                text += f"{v}\n"
        if geo:
            text += f"\n<b>Геолокация:</b>\n"
            text += f"{geo['location']}\n"
            text += f"IP: <code>{geo['ip']}</code>\n"
            text += f"{geo['org']}\n"
            if geo["coords"]:
                text += f"Координаты: {geo['coords']}\n"
        if not info:
            text = "Не удалось получить информацию"
        await query.edit_message_text(text, reply_markup=back_button(), parse_mode="HTML")

    elif query.data == "pc_control":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Выключить ПК", callback_data="pc_off")],
            [InlineKeyboardButton("Перезагрузить", callback_data="pc_restart")],
            [InlineKeyboardButton("Спящий режим", callback_data="pc_sleep")],
            [InlineKeyboardButton("Заблокировать", callback_data="pc_lock")],
            [InlineKeyboardButton("Назад", callback_data="back")],
        ])
        await query.edit_message_text("Управление ПК:", reply_markup=kb)

    elif query.data == "pc_off":
        await query.edit_message_text("ПК выключается!", reply_markup=back_button())
        subprocess.run(["shutdown", "/s", "/t", "10"])

    elif query.data == "pc_restart":
        await query.edit_message_text("ПК перезагружается!", reply_markup=back_button())
        subprocess.run(["shutdown", "/r", "/t", "10"])

    elif query.data == "pc_sleep":
        await query.edit_message_text("Спящий режим!", reply_markup=back_button())
        subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])

    elif query.data == "pc_lock":
        await query.edit_message_text("ПК заблокирован!")
        subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"])

    elif query.data == "kill":
        procs = []
        for p in psutil.process_iter(["pid", "name"]):
            try:
                info = p.info
                if info["name"] and info["pid"] != os.getpid():
                    try:
                        p.cpu_percent(interval=0)
                    except Exception:
                        pass
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        import time as _t
        _t.sleep(0.3)
        for p in psutil.process_iter(["pid", "name"]):
            try:
                info = p.info
                if info["name"] and info["pid"] != os.getpid():
                    try:
                        cpu = p.cpu_percent(interval=0)
                    except Exception:
                        cpu = 0
                    info["cpu_percent"] = cpu
                    procs.append(info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        procs.sort(key=lambda x: x.get("cpu_percent") or 0, reverse=True)
        text = "<b>Процессы (по CPU):</b>\n\n"
        shown = []
        seen_names = set()
        for p in procs:
            name = p["name"]
            if name.lower() not in seen_names:
                seen_names.add(name.lower())
                shown.append(p)
            if len(shown) >= 25:
                break
        for i, p in enumerate(shown, 1):
            cpu = p.get("cpu_percent") or 0
            text += f"  {p['pid']}. {p['name']} | CPU: {cpu}%\n"
        text += "\nНапиши PID или название процесса для завершения:"
        await query.edit_message_text(text, reply_markup=back_button(), parse_mode="HTML")
        context.user_data["waiting_for_kill"] = True

    elif query.data == "kill_system":
        await query.edit_message_text("Нельзя убивать системные процессы!")
        context.user_data.pop("waiting_for_kill", None)

    elif query.data == "files":
        chat_id = update.effective_chat.id
        if chat_id is None:
            await query.answer("Ошибка: не удалось определить чат.", show_alert=True)
            return
        msgid = await fm_send_listing(context, chat_id)
        if msgid is not None:
            context.user_data["_fm_active"] = msgid
            context.user_data["_fm_mode"] = True

    elif query.data.startswith("fm:"):
        await fm_handle(update, context)
        return

    elif query.data == "launch":
        programs = get_desktop_programs()
        if not programs:
            await query.edit_message_text("Программы на рабочем столе не найдены.", reply_markup=back_button())
            return
        text = "<b>Программы на рабочем столе:</b>\n\n"
        for i, p in enumerate(programs, 1):
            text += f"  {i}. {p}\n"
        text += "\nНапиши название программы для запуска:"
        await query.edit_message_text(text, reply_markup=back_button(), parse_mode="HTML")
        context.user_data["waiting_for_program"] = True

    elif query.data == "show_image":
        await query.edit_message_text(
            "На сколько секунд показать?",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("5 сек", callback_data="img_dur_5"),
                    InlineKeyboardButton("10 сек", callback_data="img_dur_10"),
                    InlineKeyboardButton("30 сек", callback_data="img_dur_30"),
                    InlineKeyboardButton("60 сек", callback_data="img_dur_60"),
                ],
                [InlineKeyboardButton("Назад", callback_data="back")],
            ]),
        )

    elif query.data.startswith("img_dur_"):
        dur = int(query.data.split("_")[2])
        context.user_data["image_duration"] = dur
        context.user_data["waiting_for_image"] = True
        await query.edit_message_text(
            f"Отправь картинку, покажу на {dur} сек:",
            reply_markup=back_button(),
        )

    elif query.data == "stream":
        if context.user_data.get("streaming"):
            context.user_data["streaming"] = False
            await query.edit_message_text(
                "Трансляция остановлена.", reply_markup=main_menu(),
            )
        else:
            await query.edit_message_text(
                "Выбери интервал:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("1 сек", callback_data="stream_1")],
                    [InlineKeyboardButton("3 сек", callback_data="stream_3")],
                    [InlineKeyboardButton("5 сек", callback_data="stream_5")],
                    [InlineKeyboardButton("10 сек", callback_data="stream_10")],
                    [InlineKeyboardButton("Назад", callback_data="back")],
                ]),
            )

    elif query.data.startswith("stream_"):
        interval = int(query.data.split("_")[1])
        context.user_data["streaming"] = True
        context.user_data["stream_interval"] = interval
        await query.edit_message_text(
            f"Трансляция запущена (каждые {interval} сек).\n"
            "Нажми «Трансляция» чтобы остановить.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Остановить", callback_data="stream")],
            ]),
        )
        asyncio.create_task(_run_stream(update, context, interval))

    elif query.data == "open_site":
        await query.edit_message_text(
            "Напиши ссылку (напр. https://google.com):",
            reply_markup=back_button(),
        )
        context.user_data["waiting_for_site"] = True

    elif query.data == "music":
        track = await get_current_track()
        if track:
            text = f"<b>Сейчас играет:</b>\n<i>{html.escape(track)}</i>"
        else:
            text = "Музыка не играет"
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("⏮️", callback_data="music_prev"),
                    InlineKeyboardButton("⏯️", callback_data="music_pause"),
                    InlineKeyboardButton("⏭️", callback_data="music_next"),
                ],
                [InlineKeyboardButton("Обновить", callback_data="music")],
                [InlineKeyboardButton("Назад", callback_data="back")],
            ]),
            parse_mode="HTML",
        )

    elif query.data.startswith("music_"):
        action = query.data.split("_")[1]
        await control_media(action)
        await asyncio.sleep(1)
        track = await get_current_track()
        if track:
            text = f"<b>Сейчас играет:</b>\n<i>{html.escape(track)}</i>"
        else:
            text = "Музыка не играет"
        try:
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("⏮️", callback_data="music_prev"),
                        InlineKeyboardButton("⏯️", callback_data="music_pause"),
                        InlineKeyboardButton("⏭️", callback_data="music_next"),
                    ],
                    [InlineKeyboardButton("Обновить", callback_data="music")],
                    [InlineKeyboardButton("Назад", callback_data="back")],
                ]),
                parse_mode="HTML",
            )
        except Exception:
            await query.answer()

    elif query.data == "volume":
        vol = await asyncio.to_thread(get_volume)
        await query.edit_message_text(
            f"Громкость: {vol}%",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Выключить", callback_data="vol_set_0")],
                [
                    InlineKeyboardButton("25%", callback_data="vol_set_25"),
                    InlineKeyboardButton("50%", callback_data="vol_set_50"),
                    InlineKeyboardButton("75%", callback_data="vol_set_75"),
                ],
                [InlineKeyboardButton("Полная", callback_data="vol_set_100")],
                [InlineKeyboardButton("Назад", callback_data="back")],
            ]),
        )

    elif query.data == "error_popup":
        await query.edit_message_text(
            "Какой тип ошибки?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Экран (полноэкранная)", callback_data="errtype_fullscreen")],
                [InlineKeyboardButton("Windows-стиль (MsgBox)", callback_data="errtype_msgbox")],
                [InlineKeyboardButton("Назад", callback_data="back")],
            ]),
        )

    elif query.data.startswith("vol_set_"):
        level = int(query.data.split("_")[2])
        await asyncio.to_thread(set_volume, level)
        await query.edit_message_text(
            f"Громкость: {level}%",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Выключить", callback_data="vol_set_0")],
                [
                    InlineKeyboardButton("25%", callback_data="vol_set_25"),
                    InlineKeyboardButton("50%", callback_data="vol_set_50"),
                    InlineKeyboardButton("75%", callback_data="vol_set_75"),
                ],
                [InlineKeyboardButton("Полная", callback_data="vol_set_100")],
                [InlineKeyboardButton("Назад", callback_data="back")],
            ]),
        )

    elif query.data == "vol_custom":
        await query.edit_message_text(
            "Напиши громкость (0-100):",
            reply_markup=back_button(),
        )
        context.user_data["waiting_for_volume"] = True

    elif query.data == "errtype_fullscreen":
        context.user_data["error_type"] = "fullscreen"
        context.user_data["waiting_for_error_text"] = True
        await query.edit_message_text(
            "Напиши текст ошибки:",
            reply_markup=back_button(),
        )

    elif query.data == "errtype_msgbox":
        context.user_data["error_type"] = "msgbox"
        context.user_data["waiting_for_error_text"] = True
        await query.edit_message_text(
            "Напиши текст ошибки:",
            reply_markup=back_button(),
        )


async def kill_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uname = user.username or "нет"
    name = update.message.text.strip()
    context.user_data.pop("waiting_for_kill", None)

    SYSTEM_PROCS = ["explorer.exe", "svchost.exe", "csrss.exe", "smss.exe", "lsass.exe",
                    "wininit.exe", "services.exe", "dwm.exe", "conhost.exe", "sihost.exe",
                    "taskhostw.exe", "runtimebroker.exe", "shellexperiencehost.exe",
                    "searchhost.exe", "startmenuexperiencehost.exe", "fontdrvhost.exe",
                    "python.exe", "panel.py"]

    if name.lower() in [s.lower() for s in SYSTEM_PROCS]:
        await update.message.reply_text(
            "Нельзя убивать системные процессы!", reply_markup=back_button(),
        )
        return

    killed = []
    failed = []

    if name.isdigit():
        pid = int(name)
        try:
            p = psutil.Process(pid)
            pname = p.name()
            if pname.lower() in [s.lower() for s in SYSTEM_PROCS]:
                await update.message.reply_text(
                    "Нельзя убивать системные процессы!", reply_markup=back_button(),
                )
                return
            try:
                p.kill()
                killed.append(f"{pname} (PID: {pid})")
            except psutil.AccessDenied:
                failed.append(f"{pname} (PID: {pid}) — нет прав")
        except psutil.NoSuchProcess:
            all_pids = [str(p.info["pid"]) for p in psutil.process_iter(["pid"])]
            await update.message.reply_text(
                f"Процесс с PID {name} не найден.\n"
                f"Активных процессов: {len(all_pids)}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Ещё процесс", callback_data="kill")],
                    [InlineKeyboardButton("Назад", callback_data="back")],
                ]),
            )
            return
    else:
        for p in psutil.process_iter(["pid", "name"]):
            try:
                if p.info["name"] and name.lower() in p.info["name"].lower():
                    pid = p.info["pid"]
                    pname = p.info["name"]
                    try:
                        p.kill()
                        killed.append(f"{pname} (PID: {pid})")
                    except psutil.AccessDenied:
                        failed.append(f"{pname} (PID: {pid}) — нет прав")
                    except psutil.NoSuchProcess:
                        pass
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    if killed:
        log_event(user.id, uname, user.first_name, f"убил процесс: {name} ({len(killed)} шт.)")
        update_user(user.id, uname, user.first_name, f"убил процесс: {name}")
        text = f"Убито ({len(killed)}):\n" + "\n".join(killed)
        if failed:
            text += "\n\nНет прав:\n" + "\n".join(failed)
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Ещё процесс", callback_data="kill")],
            [InlineKeyboardButton("Назад", callback_data="back")],
        ]), parse_mode="HTML")
    else:
        text = f"Процесс '{name}' не найден."
        if failed:
            text += "\n\nНет прав:\n" + "\n".join(failed)
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Ещё процесс", callback_data="kill")],
            [InlineKeyboardButton("Назад", callback_data="back")],
        ]), parse_mode="HTML")


async def launch_program(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uname = user.username or "нет"
    name = update.message.text.strip()

    programs = get_desktop_programs()
    query_lower = name.lower()
    path = _program_cache.get(query_lower)

    if not path:
        for cached_name, cached_path in _program_cache.items():
            if query_lower in cached_name:
                path = cached_path
                name = cached_name
                break

    if not path:
        log_event(user.id, uname, user.first_name, f"программа не найдена: {name}")
        await update.message.reply_text(
            f"Программа '{name}' не найдена.\nПопробуй ещё:", reply_markup=back_button(),
        )
        return

    log_event(user.id, uname, user.first_name, f"запустил: {name}")
    update_user(user.id, uname, user.first_name, f"запустил: {name}")
    context.user_data.pop("waiting_for_program", None)

    try:
        if path.lower().endswith(".lnk"):
            shell = win32com.client.Dispatch("WScript.Shell")
            shortcut = shell.CreateShortCut(path)
            target = shortcut.TargetPath
            workdir = shortcut.WorkingDirectory
            if target:
                subprocess.Popen([target], cwd=workdir if workdir else None)
            else:
                subprocess.Popen([path], shell=True)
        else:
            subprocess.Popen([path], shell=True)
        display_name = os.path.splitext(os.path.basename(path))[0]
        await update.message.reply_text(
            f"{display_name} запущен!", reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Ещё программу", callback_data="launch")],
                [InlineKeyboardButton("Назад", callback_data="back")],
            ])
        )
    except Exception as e:
        await update.message.reply_text(
            f"Ошибка: {e}", reply_markup=back_button(),
        )


async def open_site(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["waiting_for_site"] = False
    url = update.message.text.strip()
    if not url.startswith("http"):
        url = "https://" + url
    try:
        await asyncio.to_thread(webbrowser.open, url)
        await update.message.reply_text(f"Открыт: {url}", reply_markup=back_button())
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}", reply_markup=back_button())


async def set_volume_from_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["waiting_for_volume"] = False
    text = update.message.text.strip()
    try:
        level = int(text)
        if not (0 <= level <= 100):
            raise ValueError
    except ValueError:
        await update.message.reply_text("Напиши число от 0 до 100", reply_markup=back_button())
        return
    await asyncio.to_thread(set_volume, level)
    await update.message.reply_text(f"Громкость: {level}%", reply_markup=back_button())


async def handle_error_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["waiting_for_error_text"] = False
    text = update.message.text.strip()
    user = update.effective_user
    uname = user.username or "нет"
    error_type = context.user_data.pop("error_type", "fullscreen")
    log_event(user.id, uname, user.first_name, f"показал ошибку ({error_type}): {text}")
    if error_type == "msgbox":
        await asyncio.to_thread(show_error_msgbox, text)
        await update.message.reply_text("MsgBox показан!", reply_markup=back_button())
    else:
        show_error_fullscreen(text)
        await update.message.reply_text("Ошибка показана на экране!", reply_markup=back_button())


def show_image_fullscreen(path, duration=10):
    script_path = os.path.join(tempfile.gettempdir(), "show_img.py")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(
            "import tkinter as tk\n"
            "from PIL import Image, ImageTk\n"
            f"p = r'{path}'\n"
            f"dur = {duration}\n"
            "r = tk.Tk()\n"
            "r.attributes('-fullscreen', True)\n"
            "r.attributes('-topmost', True)\n"
            "r.configure(bg='black')\n"
            "w = r.winfo_screenwidth()\n"
            "h = r.winfo_screenheight()\n"
            "img = Image.open(p)\n"
            "img = img.resize((w, h), Image.LANCZOS)\n"
            "ph = ImageTk.PhotoImage(img)\n"
            "l = tk.Label(r, image=ph, bg='black')\n"
            "l.pack(fill='both', expand=True)\n"
            f"r.after({duration}000, r.destroy)\n"
            "r.mainloop()\n"
        )
    subprocess.Popen([sys.executable, script_path])


def show_error_fullscreen(text, duration=10):
    script_path = os.path.join(tempfile.gettempdir(), "show_error.py")
    safe_text = text.replace("'", "\\'").replace("\n", "\\n")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(
            "import tkinter as tk\n"
            f"dur = {duration}\n"
            "r = tk.Tk()\n"
            "r.attributes('-fullscreen', True)\n"
            "r.attributes('-topmost', True)\n"
            "r.configure(bg='red')\n"
            "w = r.winfo_screenwidth()\n"
            "h = r.winfo_screenheight()\n"
            f"msg = tk.Label(r, text='{safe_text}', font=('Arial', int(h * 0.08)), fg='white', bg='red', wraplength=int(w * 0.8))\n"
            "msg.pack(expand=True)\n"
            f"r.after({duration}000, r.destroy)\n"
            "r.mainloop()\n"
        )
    subprocess.Popen([sys.executable, script_path])


def show_error_msgbox(text):
    script_path = os.path.join(tempfile.gettempdir(), "show_msgbox.py")
    safe_text = text.replace("'", "''")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(
            "import ctypes\n"
            f"ctypes.windll.user32.MessageBoxW(0, '{safe_text}', 'Ошибка', 0)\n"
        )
    subprocess.Popen([sys.executable, script_path])


async def _run_stream(update, context, interval):
    chat_id = update.effective_chat.id
    msg_id = None
    while context.user_data.get("streaming"):
        try:
            img = ImageGrab.grab()
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=70)
            buf.seek(0)
            if msg_id is not None:
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                except Exception:
                    pass
            m = await context.bot.send_photo(
                chat_id=chat_id,
                photo=InputFile(buf),
                caption="LIVE",
            )
            msg_id = m.message_id
        except Exception:
            pass
        await asyncio.sleep(interval)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("authorized"):
        return
    if context.user_data.get("waiting_for_image"):
        context.user_data["waiting_for_image"] = False
        dur = context.user_data.get("image_duration", 10)
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        tmp = os.path.join(tempfile.gettempdir(), f"fullscreen_{photo.file_id}.jpg")
        await file.download_to_drive(tmp)
        show_image_fullscreen(tmp, dur)
        await update.message.reply_text(
            f"Показываю {dur} сек. Можешь пользоваться ботом.",
            reply_markup=main_menu(),
        )
    else:
        await update.message.reply_text(
            "Чтобы показать на экране — нажми «Картинка» в меню",
            reply_markup=main_menu(),
        )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("waiting_for_password"):
        return await check_password(update, context)
    if context.user_data.get("_fm_mode"):
        return await fm_handle_number(context, update)

    if context.user_data.get("waiting_for_program"):
        return await launch_program(update, context)
    if context.user_data.get("waiting_for_kill"):
        return await kill_process(update, context)
    if context.user_data.get("waiting_for_site"):
        return await open_site(update, context)
    if context.user_data.get("waiting_for_volume"):
        return await set_volume_from_text(update, context)
    if context.user_data.get("waiting_for_error_text"):
        return await handle_error_text(update, context)


def get_cpu_temp():
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            for name, entries in temps.items():
                if entries:
                    return f"{entries[0].current}°C"
    except Exception:
        pass
    return "нет данных"


async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uname = user.username or "нет"
    if user.id not in authorized_users:
        await update.message.reply_text("Нет доступа.")
        return
    log_event(user.id, uname, user.first_name, "запросил логи")
    update_user(user.id, uname, user.first_name, "запросил логи")
    logs = get_logs(30)
    if len(logs) > 3000:
        with open(os.path.join("logs", "logs_view.txt"), "w", encoding="utf-8") as f:
            f.write(logs)
        await update.message.reply_document(document=open(os.path.join("logs", "logs_view.txt"), "rb"))
    else:
        await update.message.reply_text(f"<b>Логи:</b>\n\n<code>{logs}</code>", parse_mode="HTML")


async def screenshotoff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    enabled = context.user_data.get("screenshot_enabled", True)
    context.user_data["screenshot_enabled"] = not enabled
    status = "включён" if not enabled else "выключен"
    await update.message.reply_text(f"Скриншот {status}")


def main():
    global authorized_users
    for uid, data in load_users().items():
        if data.get("authorized"):
            authorized_users.add(int(uid))

    app = Application.builder().token(config.BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("logs", logs_command))
    app.add_handler(CommandHandler("screenshotoff", screenshotoff))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)

    print("Бот запущен!")
    app.run_polling()


if __name__ == "__main__":
    main()
