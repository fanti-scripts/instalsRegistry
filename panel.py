import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
import re
import time
import subprocess
import psutil
import requests

USERS_FILE = "users.json"
LOG_FILE = os.path.join("logs", "bot_log.txt")
CONSOLE_FILE = os.path.join("logs", "bot_console.txt")
BOT_TOKEN = None
BOT_SCRIPT = "bot.py"

BG = "#0d0d0d"
BG2 = "#1a1a1a"
BG3 = "#252525"
FG = "#e0e0e0"
FG2 = "#999999"
ACCENT = "#58a6ff"
RED = "#da3633"
GREEN = "#238636"
BLUE = "#1f6feb"


def load_config():
    global BOT_TOKEN
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    import config
    BOT_TOKEN = config.BOT_TOKEN


def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


def get_logs():
    if not os.path.exists(LOG_FILE):
        return []
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
    pattern = r"\[(\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}:\d{2})\] ID:(\d+) \| @(\S+) \| (.+?) \| (.+)"
    entries = []
    for line in reversed(lines[-500:]):
        m = re.match(pattern, line.strip())
        if m:
            entries.append({
                "time": m.group(1),
                "user_id": m.group(2),
                "username": m.group(3),
                "first_name": m.group(4),
                "action": m.group(5),
            })
    return entries


def build_unique_users(logs, users_data):
    unique = {}
    for entry in logs:
        uid = entry["user_id"]
        if uid not in unique:
            u = users_data.get(uid, {})
            unique[uid] = {
                "id": uid,
                "username": entry["username"],
                "name": entry["first_name"],
                "action": entry["action"],
                "banned": u.get("banned", False),
            }
    for uid, u in users_data.items():
        if uid not in unique:
            unique[uid] = {
                "id": uid,
                "username": u.get("username", "?"),
                "name": u.get("first_name", "?"),
                "action": u.get("last_action", "-"),
                "banned": u.get("banned", False),
            }
    return unique


def find_bot_pid():
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if proc.info["cmdline"] and any("bot.py" in c for c in proc.info["cmdline"]):
                return proc.info["pid"]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


class Panel(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PC Control Panel")
        self.geometry("950x620")
        self.configure(bg=BG)
        self.resizable(True, True)

        self.current_tab = "logs"
        self._refresh_id = None
        self._all_logs = []
        self._all_users = {}
        self._bot_start_time = None
        self._bot_process = None

        self.build_ui()
        self.refresh_data()
        self.auto_refresh()

    def build_ui(self):
        top = tk.Frame(self, bg=BG2, height=44)
        top.pack(fill="x")
        top.pack_propagate(False)

        tk.Label(top, text="PC Control Panel", bg=BG2, fg=ACCENT,
                 font=("Segoe UI", 14, "bold")).pack(side="left", padx=12)

        self.clock_label = tk.Label(top, bg=BG2, fg=FG2, font=("Consolas", 11))
        self.clock_label.pack(side="right", padx=12)
        self.update_clock()

        nav = tk.Frame(self, bg=BG)
        nav.pack(fill="x", padx=10, pady=(10, 0))

        self.nav_btns = {}
        for text, key in [("  Logs  ", "logs"), ("  Users  ", "users"), ("  Бот  ", "bot"), ("  Ошибки  ", "errors")]:
            btn = tk.Button(nav, text=text, bg=BG if key != "logs" else BG3,
                            fg=ACCENT if key == "logs" else FG2,
                            activebackground=BG3, activeforeground=ACCENT,
                            relief="flat", font=("Segoe UI", 11, "bold" if key == "logs" else ""),
                            bd=0, cursor="hand2",
                            command=lambda k=key: self.show_tab(k))
            btn.pack(side="left", padx=(0, 4), ipady=4)
            self.nav_btns[key] = btn

        tk.Frame(self, bg="#333", height=1).pack(fill="x", padx=10, pady=(10, 0))

        sf = tk.Frame(self, bg=BG)
        sf.pack(fill="x", padx=10, pady=8)

        self.stat_labels = {}
        for i, (key, label) in enumerate([
            ("total_users", "Юзеров"), ("total_actions", "Действий"),
            ("banned", "Забанено"),             ("online", "Тотал")
        ]):
            c = tk.Frame(sf, bg=BG2, padx=20, pady=10)
            c.grid(row=0, column=i, padx=5, sticky="nsew")
            sf.columnconfigure(i, weight=1)
            n = tk.Label(c, text="0", bg=BG2, fg=ACCENT, font=("Segoe UI", 20, "bold"))
            n.pack()
            l = tk.Label(c, text=label, bg=BG2, fg=FG2, font=("Segoe UI", 9))
            l.pack()
            self.stat_labels[key] = n

        self.content = tk.Frame(self, bg=BG)
        self.content.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.build_logs_tab()
        self.build_users_tab()
        self.build_bot_tab()
        self.build_errors_tab()
        self.show_tab("logs")

    def build_logs_tab(self):
        self.logs_frame = tk.Frame(self.content, bg=BG)

        search_bar = tk.Frame(self.logs_frame, bg=BG)
        search_bar.pack(fill="x", pady=(0, 6))

        tk.Label(search_bar, text="Поиск:", bg=BG, fg=FG2,
                 font=("Segoe UI", 10)).pack(side="left", padx=(0, 6))

        self.log_search_var = tk.StringVar()
        self.log_search_var.trace_add("write", lambda *a: self.filter_logs())
        log_entry = tk.Entry(search_bar, textvariable=self.log_search_var,
                             bg="#111", fg=FG, insertbackground=FG,
                             font=("Segoe UI", 10), relief="flat", bd=0)
        log_entry.pack(side="left", fill="x", expand=True, ipady=4, padx=(0, 6))

        self.log_text = tk.Text(self.logs_frame, bg="#111", fg=FG2,
                                font=("Consolas", 10), relief="flat", wrap="word",
                                insertbackground=FG2,
                                padx=10, pady=10, selectbackground="#333",
                                selectforeground=FG)
        sb = ttk.Scrollbar(self.logs_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log_text.pack(fill="both", expand=True)

        self.log_text.tag_configure("time", foreground=ACCENT)
        self.log_text.tag_configure("id", foreground="#f0883e")
        self.log_text.tag_configure("user", foreground="#7ee787")
        self.log_text.tag_configure("action", foreground="#d2a8ff")

    def build_users_tab(self):
        self.users_frame = tk.Frame(self.content, bg=BG)

        bb = tk.Frame(self.users_frame, bg=BG)
        bb.pack(fill="x", pady=(0, 6))

        for text, color, cmd in [
            ("Забанить", RED, self.ban_selected),
            ("Разбанить", GREEN, self.unban_selected),
            ("Сообщение от бота", BLUE, self.send_message),
            ("Удалить", "#888", self.delete_selected),
        ]:
            btn = tk.Button(bb, text=text, bg=BG2, fg=color, activebackground=BG3,
                            activeforeground=color, relief="flat", font=("Segoe UI", 10, "bold"),
                            bd=1, cursor="hand2", command=cmd,
                            highlightbackground=color, highlightthickness=1)
            btn.pack(side="left", padx=4, ipadx=14, ipady=5)

        tk.Button(bb, text="Обновить", bg=BG2, fg=FG2, activebackground=BG3,
                  activeforeground=FG, relief="flat", font=("Segoe UI", 10),
                  bd=1, cursor="hand2", command=self.refresh_data,
                  highlightbackground="#444", highlightthickness=1
                  ).pack(side="right", padx=4, ipadx=14, ipady=5)

        search_bar = tk.Frame(self.users_frame, bg=BG)
        search_bar.pack(fill="x", pady=(0, 6))

        tk.Label(search_bar, text="Поиск:", bg=BG, fg=FG2,
                 font=("Segoe UI", 10)).pack(side="left", padx=(0, 6))

        self.user_search_var = tk.StringVar()
        self.user_search_var.trace_add("write", lambda *a: self.filter_users())
        tk.Entry(search_bar, textvariable=self.user_search_var,
                 bg="#111", fg=FG, insertbackground=FG,
                 font=("Segoe UI", 10), relief="flat", bd=0
                 ).pack(side="left", fill="x", expand=True, ipady=4)

        tree_frame = tk.Frame(self.users_frame, bg=BG)
        tree_frame.pack(fill="both", expand=True)

        columns = ("id", "username", "name", "last_action", "status")
        self.tree = ttk.Treeview(tree_frame, columns=columns,
                                 show="headings", selectmode="browse")
        self.tree.heading("id", text="ID")
        self.tree.heading("username", text="Username")
        self.tree.heading("name", text="Имя")
        self.tree.heading("last_action", text="Последнее действие")
        self.tree.heading("status", text="Статус")
        self.tree.column("id", width=100)
        self.tree.column("username", width=130)
        self.tree.column("name", width=130)
        self.tree.column("last_action", width=280)
        self.tree.column("status", width=80)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", background="#111", foreground=FG,
                        fieldbackground="#111", font=("Segoe UI", 10), rowheight=28)
        style.configure("Treeview.Heading", background=BG2, foreground=ACCENT,
                        font=("Segoe UI", 10, "bold"))
        style.map("Treeview", background=[("selected", "#333")],
                  foreground=[("selected", ACCENT)])

        ts = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=ts.set)
        ts.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)

    def build_bot_tab(self):
        self.bot_frame = tk.Frame(self.content, bg=BG)

        info_frame = tk.Frame(self.bot_frame, bg=BG2, padx=20, pady=15)
        info_frame.pack(fill="x", padx=10, pady=10)

        tk.Label(info_frame, text="Управление ботом", bg=BG2, fg=ACCENT,
                 font=("Segoe UI", 14, "bold")).pack(anchor="w")

        self.bot_status_label = tk.Label(info_frame, text="Статус: проверяю...",
                                         bg=BG2, fg=FG2, font=("Segoe UI", 11))
        self.bot_status_label.pack(anchor="w", pady=(8, 0))

        self.bot_uptime_label = tk.Label(info_frame, text="Время работы: --",
                                         bg=BG2, fg=FG2, font=("Segoe UI", 11))
        self.bot_uptime_label.pack(anchor="w", pady=(4, 0))

        self.bot_pid_label = tk.Label(info_frame, text="PID: --",
                                      bg=BG2, fg=FG2, font=("Segoe UI", 11))
        self.bot_pid_label.pack(anchor="w", pady=(4, 0))

        btn_frame = tk.Frame(self.bot_frame, bg=BG)
        btn_frame.pack(fill="x", padx=10, pady=10)

        self.btn_bot_start = tk.Button(btn_frame, text="Запустить", bg=BG2, fg=GREEN,
                                       activebackground=BG3, activeforeground=GREEN,
                                       relief="flat", font=("Segoe UI", 11, "bold"),
                                       bd=1, cursor="hand2", command=self.start_bot,
                                       highlightbackground=GREEN, highlightthickness=1)
        self.btn_bot_start.pack(side="left", padx=5, ipadx=20, ipady=8)

        self.btn_bot_stop = tk.Button(btn_frame, text="Остановить", bg=BG2, fg=RED,
                                      activebackground=BG3, activeforeground=RED,
                                      relief="flat", font=("Segoe UI", 11, "bold"),
                                      bd=1, cursor="hand2", command=self.stop_bot,
                                      highlightbackground=RED, highlightthickness=1)
        self.btn_bot_stop.pack(side="left", padx=5, ipadx=20, ipady=8)

        self.btn_bot_restart = tk.Button(btn_frame, text="Перезапуск", bg=BG2, fg=ACCENT,
                                         activebackground=BG3, activeforeground=ACCENT,
                                         relief="flat", font=("Segoe UI", 11, "bold"),
                                         bd=1, cursor="hand2", command=self.restart_bot,
                                         highlightbackground=ACCENT, highlightthickness=1)
        self.btn_bot_restart.pack(side="left", padx=5, ipadx=20, ipady=8)

        log_frame = tk.Frame(self.bot_frame, bg=BG)
        log_frame.pack(fill="both", expand=True, padx=10, pady=(5, 0))

        tk.Label(log_frame, text="Логи бота:", bg=BG, fg=FG2,
                 font=("Segoe UI", 10)).pack(anchor="w")

        self.bot_log_text = tk.Text(log_frame, bg="#111", fg=FG2,
                                    font=("Consolas", 10), relief="flat", wrap="word",
                                    padx=10, pady=10, height=12)
        bs = ttk.Scrollbar(log_frame, command=self.bot_log_text.yview)
        self.bot_log_text.configure(yscrollcommand=bs.set)
        bs.pack(side="right", fill="y")
        self.bot_log_text.pack(fill="both", expand=True)

    def build_errors_tab(self):
        self.errors_frame = tk.Frame(self.content, bg=BG)

        tk.Label(self.errors_frame, text="Консоль бота:", bg=BG, fg=FG2,
                 font=("Segoe UI", 10)).pack(anchor="w")

        self.errors_text = tk.Text(self.errors_frame, bg="#111", fg="#ff6666",
                                    font=("Consolas", 10), relief="flat", wrap="word",
                                    padx=10, pady=10, height=15)
        bs = ttk.Scrollbar(self.errors_frame, command=self.errors_text.yview)
        self.errors_text.configure(yscrollcommand=bs.set)
        bs.pack(side="right", fill="y")
        self.errors_text.pack(fill="both", expand=True)

    def refresh_bot_status(self):
        pid = find_bot_pid()
        if pid:
            try:
                proc = psutil.Process(pid)
                create_time = proc.create_time()
                uptime_sec = time.time() - create_time
                h = int(uptime_sec // 3600)
                m = int((uptime_sec % 3600) // 60)
                s = int(uptime_sec % 60)
                self.bot_status_label.configure(text="Статус: запущен", fg=GREEN)
                self.bot_uptime_label.configure(text=f"Время работы: {h}ч {m}м {s}с")
                self.bot_pid_label.configure(text=f"PID: {pid}")
            except psutil.NoSuchProcess:
                self.bot_status_label.configure(text="Статус: не найден", fg=RED)
                self.bot_uptime_label.configure(text="Время работы: --")
                self.bot_pid_label.configure(text="PID: --")
        else:
            self.bot_status_label.configure(text="Статус: остановлен", fg=RED)
            self.bot_uptime_label.configure(text="Время работы: --")
            self.bot_pid_label.configure(text="PID: --")

        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
            self.bot_log_text.configure(state="normal")
            self.bot_log_text.delete("1.0", "end")
            self.bot_log_text.insert("end", "".join(lines[-60:]))
            self.bot_log_text.see("end")

    def start_bot(self):
        pid = find_bot_pid()
        if pid:
            messagebox.showinfo("Инфо", "Бот уже запущен")
            return
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), BOT_SCRIPT)
        self._bot_process = subprocess.Popen(
            ["python", script],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self._bot_start_time = time.time()
        self.refresh_bot_status()
        messagebox.showinfo("Готово", "Бот запущен")

    def stop_bot(self):
        pid = find_bot_pid()
        if not pid:
            messagebox.showinfo("Инфо", "Бот не запущен")
            return
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            self._bot_start_time = None
            self.refresh_bot_status()
            messagebox.showinfo("Готово", "Бот остановлен")
        except psutil.NoSuchProcess:
            messagebox.showwarning("Внимание", "Процесс не найден")

    def restart_bot(self):
        pid = find_bot_pid()
        if pid:
            try:
                psutil.Process(pid).terminate()
            except psutil.NoSuchProcess:
                pass
        time.sleep(1)
        self.start_bot()

    def auto_refresh(self):
        self.refresh_data()
        if self.current_tab == "bot":
            self.refresh_bot_status()
        if self.current_tab == "errors":
            self.refresh_errors()
        self._refresh_id = self.after(5000, self.auto_refresh)

    def show_tab(self, tab):
        self.current_tab = tab
        self.logs_frame.pack_forget()
        self.users_frame.pack_forget()
        self.bot_frame.pack_forget()
        self.errors_frame.pack_forget()

        for key, btn in self.nav_btns.items():
            if key == tab:
                btn.configure(bg=BG3, fg=ACCENT, font=("Segoe UI", 11, "bold"))
            else:
                btn.configure(bg=BG, fg=FG2, font=("Segoe UI", 11))

        if tab == "logs":
            self.logs_frame.pack(fill="both", expand=True)
        elif tab == "users":
            self.users_frame.pack(fill="both", expand=True)
        elif tab == "errors":
            self.refresh_errors()
            self.errors_frame.pack(fill="both", expand=True)
        else:
            self.bot_frame.pack(fill="both", expand=True)

    def refresh_errors(self):
        if not os.path.exists(CONSOLE_FILE):
            return
        with open(CONSOLE_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        self.errors_text.configure(state="normal")
        self.errors_text.delete("1.0", "end")
        self.errors_text.insert("end", "".join(lines[-100:]))
        self.errors_text.see("end")

    def refresh_data(self):
        self._all_logs = get_logs()
        users_data = load_users()
        self._all_users = build_unique_users(self._all_logs, users_data)

        self.filter_logs()
        self.filter_users()

        self.stat_labels["total_users"].configure(text=str(len(self._all_users)))
        self.stat_labels["total_actions"].configure(text=str(len(self._all_logs)))
        self.stat_labels["banned"].configure(
            text=str(sum(1 for u in self._all_users.values() if u["banned"])))
        self.stat_labels["online"].configure(text=str(len(self._all_users)))

    def filter_logs(self):
        query = self.log_search_var.get().lower()
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        for entry in self._all_logs:
            line = f"[{entry['time']}] ID:{entry['user_id']} | @{entry['username']} | {entry['action']}\n"
            if query and query not in line.lower():
                continue
            self.log_text.insert("end", line, "time")

    def filter_users(self):
        query = self.user_search_var.get().lower()
        for item in self.tree.get_children():
            self.tree.delete(item)
        for u in self._all_users.values():
            status = "Забанен" if u["banned"] else "Активен"
            row = f"{u['id']} {u['username']} {u['name']} {u['action']} {status}".lower()
            if query and query not in row:
                continue
            self.tree.insert("", "end", values=(
                u["id"], u["username"], u["name"], u["action"], status
            ))

    def update_clock(self):
        self.clock_label.configure(text=time.strftime("%H:%M:%S"))
        self.after(1000, self.update_clock)

    def get_selected_user(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Внимание", "Выбери пользователя в таблице")
            return None
        return str(self.tree.item(sel[0])["values"][0])

    def ban_selected(self):
        uid = self.get_selected_user()
        if not uid:
            return
        users = load_users()
        if uid not in users:
            users[uid] = {}
        users[uid]["banned"] = True
        save_users(users)
        self.refresh_data()
        messagebox.showinfo("Готово", f"Пользователь {uid} забанен")

    def unban_selected(self):
        uid = self.get_selected_user()
        if not uid:
            return
        users = load_users()
        if uid not in users:
            users[uid] = {"banned": False}
        else:
            users[uid]["banned"] = False
        save_users(users)
        self.refresh_data()
        messagebox.showinfo("Готово", f"Пользователь {uid} разбанен")

    def delete_selected(self):
        uid = self.get_selected_user()
        if not uid:
            return
        if not messagebox.askyesno("Подтверждение", f"Удалить пользователя {uid} из логов и базы?"):
            return

        users = load_users()
        if uid in users:
            del users[uid]
            save_users(users)

        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                for line in lines:
                    if f"ID:{uid} |" not in line:
                        f.write(line)

        self.refresh_data()
        messagebox.showinfo("Готово", f"Пользователь {uid} удалён")

    def send_message(self):
        uid = self.get_selected_user()
        if not uid:
            return

        d = tk.Toplevel(self)
        d.title("Отправить сообщение")
        d.geometry("420x210")
        d.configure(bg=BG)
        d.transient(self)
        d.grab_set()

        tk.Label(d, text=f"Получатель: {uid}", bg=BG, fg=FG2,
                 font=("Segoe UI", 10)).pack(pady=(12, 6))

        sv = tk.StringVar()
        e = tk.Entry(d, textvariable=sv, bg="#111", fg=FG, insertbackground=FG,
                     font=("Segoe UI", 11), relief="flat", bd=0)
        e.pack(fill="x", padx=20, ipady=6)
        e.focus()

        def send():
            txt = sv.get().strip()
            if not txt:
                messagebox.showwarning("Внимание", "Введите сообщение", parent=d)
                return
            try:
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                r = requests.post(url, json={"chat_id": int(uid), "text": txt}, timeout=10)
                if r.status_code == 200 and r.json().get("ok"):
                    messagebox.showinfo("Готово", "Сообщение отправлено", parent=d)
                    d.destroy()
                else:
                    messagebox.showerror("Ошибка", r.text, parent=d)
            except Exception as ex:
                messagebox.showerror("Ошибка", str(ex), parent=d)

        tk.Button(d, text="Отправить", bg=BG2, fg=ACCENT, activebackground=BG3,
                  activeforeground=ACCENT, relief="flat", font=("Segoe UI", 10),
                  bd=1, cursor="hand2", command=send,
                  highlightbackground=ACCENT, highlightthickness=1).pack(pady=12, ipadx=20, ipady=4)


if __name__ == "__main__":
    load_config()
    app = Panel()
    app.mainloop()
