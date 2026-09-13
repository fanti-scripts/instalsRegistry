import math
import os
import html
import zipfile
import tempfile
import shutil
import asyncio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile

FM_PAGE = 30
FM_MAX_SEND = 48 * 1024 * 1024

ICONS = {
    ".txt": "📄", ".md": "📄", ".log": "📄",
    ".py": "🐍", ".js": "🟨", ".ts": "🟦", ".html": "🌐", ".css": "🎨",
    ".json": "🧩", ".xml": "🧩", ".yaml": "🧩",
    ".png": "🖼", ".jpg": "🖼", ".jpeg": "🖼", ".gif": "🖼", ".bmp": "🖼", ".ico": "🖼",
    ".mp4": "🎬", ".avi": "🎬", ".mkv": "🎬", ".mov": "🎬", ".webm": "🎬",
    ".mp3": "🎵", ".wav": "🎵", ".flac": "🎵", ".ogg": "🎵", ".m4a": "🎵",
    ".pdf": "📕", ".doc": "📘", ".docx": "📘", ".xls": "📗", ".xlsx": "📗",
    ".ppt": "📙", ".pptx": "📙",
    ".zip": "📦", ".rar": "📦", ".7z": "📦", ".gz": "📦",
    ".exe": "⚙️", ".msi": "⚙️", ".bat": "⚙️", ".cmd": "⚙️",
    ".dll": "🧩", ".lnk": "🔗", ".url": "🔗",
    ".iso": "💿", ".img": "💿",
}


def human_size(n):
    if n >= 1024 ** 3:
        return f"{n / (1024 ** 3):.1f} ГБ"
    if n >= 1024 ** 2:
        return f"{n / (1024 ** 2):.1f} МБ"
    if n >= 1024:
        return f"{n / 1024:.0f} КБ"
    return f"{n} Б"


def fm_get_drives():
    drives = []
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        p = f"{letter}:\\"
        try:
            if os.path.exists(p):
                drives.append({
                    "type": "dir", "name": f"{letter}:\\", "path": p,
                    "size": 0, "ext": "",
                })
        except OSError:
            pass
    return drives


def fm_list_dir(path):
    items = []
    try:
        with os.scandir(path) as it:
            for entry in it:
                try:
                    is_dir = entry.is_dir()
                except OSError:
                    is_dir = False
                if is_dir:
                    size = 0
                else:
                    try:
                        size = entry.stat().st_size
                    except OSError:
                        size = 0
                items.append({
                    "type": "dir" if is_dir else "file",
                    "name": entry.name,
                    "path": entry.path,
                    "size": size,
                    "ext": os.path.splitext(entry.name)[1].lower(),
                })
    except (PermissionError, OSError):
        return None
    items.sort(key=lambda x: (x["type"] != "dir", x["name"].lower()))
    return items


def fm_build(path):
    items = fm_list_dir(path)
    if items is None:
        return None
    parent = os.path.dirname(path)
    return {
        "cwd": path,
        "items": items,
        "has_parent": parent != path,
        "page": 0,
        "pages": max(1, math.ceil(len(items) / FM_PAGE)),
    }


def fm_home():
    drives = fm_get_drives()
    return {
        "cwd": "Мой ПК",
        "items": drives,
        "has_parent": False,
        "page": 0,
        "pages": max(1, math.ceil(len(drives) / FM_PAGE)),
    }


def fm_icon(item):
    if item["type"] == "dir":
        return "📁"
    return ICONS.get(item.get("ext", ""), "📄")


def fm_save(context, msgid, ctx):
    maps = context.user_data.setdefault("_fm", {})
    maps[str(msgid)] = ctx
    if len(maps) > 3:
        for key in list(maps)[:-3]:
            maps.pop(key)


def fm_load(context, msgid):
    return context.user_data.get("_fm", {}).get(str(msgid))


def fm_text(ctx):
    page = int(ctx.get("page", 0))
    start = page * FM_PAGE
    visible = ctx["items"][start:start + FM_PAGE]

    lines = [
        "<b>Файловый менеджер</b>",
        f"📍 {html.escape(ctx['cwd'])}",
        "",
    ]
    for i, item in enumerate(ctx["items"], 1):
        if start <= i - 1 < start + len(visible):
            if item["type"] == "dir":
                lines.append(f"<b>{i}.</b> 📁 <code>{html.escape(item['name'])}</code>")
            else:
                line = f"<b>{i}.</b> {fm_icon(item)} <code>{html.escape(item['name'])}</code>"
                if item["size"] > 0:
                    line += f" <i>({human_size(item['size'])})</i>"
                lines.append(line)
    lines.append("")
    if ctx["pages"] > 1:
        lines.append(f"Страница {page + 1}/{ctx['pages']} · всего {len(ctx['items'])}")
    lines.append("Напиши номер или путь (напр. C:\\Users):")
    return "\n".join(lines)


def fm_keyboard(ctx, msgid):
    rows = []
    if ctx.get("has_parent"):
        rows.append([InlineKeyboardButton("⬆️ Вверх", callback_data=f"fm:up:{msgid}")])

    if ctx["pages"] > 1:
        page = int(ctx.get("page", 0))
        rows.append([
            InlineKeyboardButton("⬅️", callback_data=f"fm:pg:{msgid}:-1"),
            InlineKeyboardButton(f"{page + 1}/{ctx['pages']}", callback_data="fm:none"),
            InlineKeyboardButton("➡️", callback_data=f"fm:pg:{msgid}:1"),
        ])

    rows.append([
        InlineKeyboardButton("🏠 Диски", callback_data=f"fm:home:{msgid}"),
        InlineKeyboardButton("В меню", callback_data="back"),
    ])
    return InlineKeyboardMarkup(rows)


def fm_select_text(item):
    header = f"{fm_icon(item)} <b>{html.escape(item['name'])}</b>"
    if item["type"] == "file" and item["size"] > 0:
        header += f"\n<i>Размер: {human_size(item['size'])}</i>"
    return header + "\n\nЧто сделать?"


def fm_select_keyboard(msgid, idx, is_dir=False):
    buttons = [
        [InlineKeyboardButton("Открыть", callback_data=f"fm:open:{msgid}:{idx}")],
        [InlineKeyboardButton("Скачать", callback_data=f"fm:dl:{msgid}:{idx}")],
    ]
    if is_dir:
        buttons.insert(1, [InlineKeyboardButton("Сжать в ZIP", callback_data=f"fm:zip:{msgid}:{idx}")])
    buttons.append([InlineKeyboardButton("Отмена", callback_data=f"fm:can:{msgid}")])
    return InlineKeyboardMarkup(buttons)


async def fm_send_listing(context, chat_id, cwd=None):
    try:
        ctx = fm_home() if cwd is None else fm_build(cwd)
        if ctx is None:
            return None
        msg = await context.bot.send_message(chat_id=chat_id, text=fm_text(ctx), parse_mode="HTML")
        fm_save(context, msg.message_id, ctx)
        await msg.edit_text(text=fm_text(ctx), reply_markup=fm_keyboard(ctx, msg.message_id), parse_mode="HTML")
        return msg.message_id
    except Exception as e:
        print(f"[FM ERROR] {e}")
        return None


async def fm_download(context, update, query, item):
    path = item["path"]
    name = item["name"]
    if item["size"] > FM_MAX_SEND:
        await query.answer(
            f"⚠️ Файл слишком большой ({human_size(item['size'])}). "
            "Telegram не разрешает отправлять файлы больше 50 МБ.",
            show_alert=True,
        )
        return
    await query.answer("Отправляю файл...")
    try:
        with open(path, "rb") as fh:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=InputFile(fh, filename=name),
            )
    except FileNotFoundError:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text="Файл уже удалён или недоступен."
        )
    except PermissionError:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text="Нет прав на чтение этого файла."
        )
    except Exception as e:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text=f"Не удалось отправить: {e}"
        )


async def fm_redraw(context, chat_id, msgid, ctx):
    fm_save(context, msgid, ctx)
    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=msgid,
        text=fm_text(ctx),
        reply_markup=fm_keyboard(ctx, msgid),
        parse_mode="HTML",
    )


async def fm_handle_number(context, update):
    text = update.message.text.strip()
    msgid = context.user_data.get("_fm_active")
    ctx = fm_load(context, msgid)

    if msgid is None or ctx is None:
        await update.message.reply_text(
            "Файловый менеджер устарел. Нажми «Файлы» в меню заново."
        )
        return

    if os.path.isabs(text) or (len(text) >= 2 and text[1] == ":"):
        path = text
        if not os.path.exists(path):
            await update.message.reply_text(f"Путь не найден: <code>{html.escape(path)}</code>", parse_mode="HTML")
            return
        if os.path.isfile(path):
            name = os.path.basename(path)
            size = 0
            try:
                size = os.path.getsize(path)
            except OSError:
                pass
            item = {"type": "file", "name": name, "path": path, "size": size, "ext": os.path.splitext(name)[1].lower()}
            await update.message.reply_text(
                fm_select_text(item),
                reply_markup=fm_select_keyboard(msgid, -1, False),
                parse_mode="HTML",
            )
        else:
            new_ctx = fm_build(path)
            if new_ctx is None:
                await update.message.reply_text("Нет доступа к папке.")
                return
            fm_save(context, msgid, new_ctx)
            await update.message.reply_text(
                fm_text(new_ctx),
                reply_markup=fm_keyboard(new_ctx, msgid),
                parse_mode="HTML",
            )
        return

    try:
        number = int(text)
    except ValueError:
        await update.message.reply_text("Напиши номер из списка или полный путь (например C:\\Users).")
        return

    idx = number - 1
    if not (0 <= idx < len(ctx["items"])):
        await update.message.reply_text(f"Нет пункта под номером {number}.")
        return

    item = ctx["items"][idx]
    await update.message.reply_text(
        fm_select_text(item),
        reply_markup=fm_select_keyboard(msgid, idx, item["type"] == "dir"),
        parse_mode="HTML",
    )


async def fm_handle(update, context):
    query = update.callback_query
    data = query.data.split(":")
    if data[0] != "fm":
        return
    op = data[1]
    msgid = int(data[2]) if len(data) > 2 else (update.effective_message.message_id if update.effective_message else 0)

    if op == "none":
        await query.answer()
        return

    ctx = fm_load(context, msgid)

    if op == "home":
        await query.answer()
        await fm_redraw(context, update.effective_chat.id, msgid, fm_home())
        return

    if not ctx:
        await query.answer()
        await query.edit_message_text(
            "Сессия истекла.\nНажми «Файлы» в меню, чтобы открыть менеджер заново.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Файлы", callback_data="files")],
            ]),
        )
        return

    if op == "pg":
        await query.answer()
        ctx["page"] = max(0, min(ctx["page"] + int(data[3]), ctx["pages"] - 1))
        await fm_redraw(context, update.effective_chat.id, msgid, ctx)
        return

    if op == "up":
        parent = os.path.dirname(ctx["cwd"])
        if parent == ctx["cwd"]:
            await query.answer("Это корень диска")
            return
        new_ctx = fm_build(parent)
        if new_ctx is None:
            await query.answer("Нет доступа к папке", show_alert=True)
            return
        await query.answer()
        await fm_redraw(context, update.effective_chat.id, msgid, new_ctx)
        return

    if op == "can":
        await query.answer("Отменено")
        try:
            await query.message.delete()
        except Exception:
            pass
        return

    if op == "zip":
        item = ctx["items"][int(data[3])]
        if item["type"] == "file":
            await query.answer("Это файл — скачай его", show_alert=True)
            return
        await query.answer("Проверяю размер...")
        folder_size = await asyncio.to_thread(fm_dir_size, item["path"])
        if folder_size > FM_MAX_SEND:
            await query.answer(
                f"⚠️ Папка слишком большая ({human_size(folder_size)}). "
                "Telegram не разрешает отправлять файлы больше 50 МБ.",
                show_alert=True,
            )
            return
        await query.answer("⏳ Сжимаю в ZIP...")
        try:
            zip_path = await _zip_dir(item["path"], item["name"])
            size = os.path.getsize(zip_path)
            if size > FM_MAX_SEND:
                await query.answer(
                    f"⚠️ Архив слишком большой ({human_size(size)}). "
                    "Telegram не разрешает отправлять файлы больше 50 МБ",
                    show_alert=True,
                )
                os.remove(zip_path)
                return
            with open(zip_path, "rb") as fh:
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=InputFile(fh, filename=f"{item['name']}.zip"),
                )
            os.remove(zip_path)
            await query.answer("Отправлено!", show_alert=True)
            try:
                await query.message.delete()
            except Exception:
                pass
        except Exception as e:
            await query.answer(f"Ошибка: {e}", show_alert=True)
            return

    if op == "zipsplit":
        item = ctx["items"][int(data[3])]
        if item["type"] == "file":
            await query.answer("Это файл — скачай его", show_alert=True)
            return
        await query.answer("Нарезаю на части...")
        try:
            zip_paths = await _zip_dir_split(item["path"], item["name"], FM_MAX_SEND - 1024 * 1024)
            if not zip_paths:
                await query.answer("Не удалось создать архивы", show_alert=True)
                return
            total = len(zip_paths)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"Нарезано на {total} частей. Отправляю...",
            )
            for i, zp in enumerate(zip_paths, 1):
                size = os.path.getsize(zp)
                with open(zp, "rb") as fh:
                    await context.bot.send_document(
                        chat_id=update.effective_chat.id,
                        document=InputFile(fh, filename=f"{item['name']}_part{i}_из_{total}.zip"),
                        caption=f"Часть {i}/{total} ({human_size(size)})",
                    )
                os.remove(zp)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"Все {total} частей отправлены.\n"
                     f"Чтобы собрать: создай папку и распакуй все zip туда.",
            )
            try:
                await query.message.delete()
            except Exception:
                pass
        except Exception as e:
            await query.answer(f"Ошибка: {e}", show_alert=True)
            return

    if op == "open":
        item = ctx["items"][int(data[3])]
        if item["type"] == "file":
            await query.answer("Это файл — нажми «Скачать»", show_alert=True)
            return
        new_ctx = fm_build(item["path"])
        if new_ctx is None:
            await query.answer("Нет доступа к папке", show_alert=True)
            return
        await query.answer()
        await fm_redraw(context, update.effective_chat.id, msgid, new_ctx)
        try:
            await query.message.delete()
        except Exception:
            pass
        return

    if op == "dl":
        item = ctx["items"][int(data[3])]
        if item["type"] == "dir":
            await query.answer("Это папка — открой её", show_alert=True)
            return
        await fm_download(context, update, query, item)
        try:
            await query.message.delete()
        except Exception:
            pass
        return


def fm_dir_size(path):
    total = 0
    for root, dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


async def _zip_dir(dir_path, name):
    def _do_zip():
        tmp = tempfile.gettempdir()
        zip_path = os.path.join(tmp, f"{name}.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(dir_path):
                for f in files:
                    full = os.path.join(root, f)
                    try:
                        arc = os.path.relpath(full, dir_path)
                        zf.write(full, arc)
                    except (PermissionError, OSError):
                        pass
        return zip_path
    return await asyncio.to_thread(_do_zip)


async def _zip_dir_split(dir_path, name, max_bytes):
    def _do_split():
        tmp = tempfile.gettempdir()
        part = 1
        zip_path = os.path.join(tmp, f"{name}_part{part}.zip")
        zf = zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED)
        current_size = 0
        results = []

        for root, dirs, files in os.walk(dir_path):
            for f in files:
                full = os.path.join(root, f)
                try:
                    arc = os.path.relpath(full, dir_path)
                    file_size = os.path.getsize(full)
                except (PermissionError, OSError):
                    continue

                if current_size + file_size > max_bytes and current_size > 0:
                    zf.close()
                    results.append(zip_path)
                    part += 1
                    zip_path = os.path.join(tmp, f"{name}_part{part}.zip")
                    zf = zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED)
                    current_size = 0

                try:
                    zf.write(full, arc)
                    current_size += file_size
                except (PermissionError, OSError):
                    pass

        zf.close()
        if os.path.getsize(zip_path) > 0:
            results.append(zip_path)
        else:
            os.remove(zip_path)
        return results
    return await asyncio.to_thread(_do_split)