import sys
import os
import subprocess
import tkinter as tk
import shutil
import winreg

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

os.chdir(BASE_DIR)

BG = "#1a1a1a"
BG2 = "#252525"
FG = "#e0e0e0"
GREEN = "#238636"
RED = "#da3633"
ACCENT = "#58a6ff"

INSTALL_DIR = os.path.join(os.environ.get("APPDATA", ""), "Registry")
BOT_EXE = os.path.join(BASE_DIR, "Registry.exe")
INSTALLED_BOT = os.path.join(INSTALL_DIR, "Registry.exe")
LAUNCHER_EXE = os.path.join(BASE_DIR, "Launcher.exe")
INSTALLED_LAUNCHER = os.path.join(INSTALL_DIR, "Launcher.exe")
AUTORUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTORUN_NAME = "RegistryBot"


def find_bot_pid():
    import psutil
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if proc.info["name"] and "Registry" in proc.info["name"]:
                return proc.info["pid"]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def stop_bot():
    import psutil
    pid = find_bot_pid()
    if pid:
        try:
            psutil.Process(pid).terminate()
        except Exception:
            pass


def is_installed():
    return os.path.exists(INSTALLED_BOT)


def install_bot():
    os.makedirs(INSTALL_DIR, exist_ok=True)
    src_bot = os.path.join(BASE_DIR, "Registry.exe")
    src_launcher = os.path.join(BASE_DIR, "Launcher.exe")
    if os.path.exists(src_bot):
        shutil.copy2(src_bot, INSTALLED_BOT)
    if os.path.exists(src_launcher):
        shutil.copy2(src_launcher, INSTALLED_LAUNCHER)
    add_autorun()


def add_autorun():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTORUN_KEY, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, AUTORUN_NAME, 0, winreg.REG_SZ, f'"{INSTALLED_LAUNCHER}"')
        winreg.CloseKey(key)
    except Exception:
        pass


def remove_autorun():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTORUN_KEY, 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, AUTORUN_NAME)
        winreg.CloseKey(key)
    except Exception:
        pass


class BotLauncher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Registry")
        self.geometry("320x240")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self._check_id = None

        top = tk.Frame(self, bg=BG2, height=40)
        top.pack(fill="x")
        top.pack_propagate(False)
        tk.Label(top, text="Registry", bg=BG2, fg=ACCENT,
                 font=("Segoe UI", 13, "bold")).pack(side="left", padx=12)

        sf = tk.Frame(self, bg=BG2, padx=15, pady=12)
        sf.pack(fill="x", padx=10, pady=10)

        tk.Label(sf, text="Статус:", bg=BG2, fg=FG,
                 font=("Segoe UI", 11)).pack(side="left")
        self.status_label = tk.Label(sf, text="Остановлен", bg=BG2, fg=RED,
                                     font=("Segoe UI", 11, "bold"))
        self.status_label.pack(side="left", padx=(8, 0))

        bf = tk.Frame(self, bg=BG)
        bf.pack(fill="x", padx=10, pady=(0, 10))

        self.btn_start = tk.Button(bf, text="Старт", bg=BG2, fg=GREEN,
                                   activebackground=BG2, activeforeground=GREEN,
                                   relief="flat", font=("Segoe UI", 11, "bold"),
                                   bd=1, cursor="hand2", command=self.start_bot,
                                   highlightbackground=GREEN, highlightthickness=1,
                                   width=12)
        self.btn_start.pack(side="left", padx=4, ipady=4)

        self.btn_stop = tk.Button(bf, text="Стоп", bg=BG2, fg=RED,
                                  activebackground=BG2, activeforeground=RED,
                                  relief="flat", font=("Segoe UI", 11, "bold"),
                                  bd=1, cursor="hand2", command=self.stop_bot,
                                  highlightbackground=RED, highlightthickness=1,
                                  width=12)
        self.btn_stop.pack(side="left", padx=4, ipady=4)

        af = tk.Frame(self, bg=BG)
        af.pack(fill="x", padx=10, pady=(0, 5))

        self.btn_install = tk.Button(af, text="Установить", bg=BG2, fg=ACCENT,
                                     activebackground=BG2, activeforeground=ACCENT,
                                     relief="flat", font=("Segoe UI", 10, "bold"),
                                     bd=1, cursor="hand2", command=self.install_bot,
                                     highlightbackground=ACCENT, highlightthickness=1,
                                     width=12)
        self.btn_install.pack(side="left", padx=4, ipady=4)

        self.btn_uninstall = tk.Button(af, text="Удалить", bg=BG2, fg=RED,
                                       activebackground=BG2, activeforeground=RED,
                                       relief="flat", font=("Segoe UI", 10, "bold"),
                                       bd=1, cursor="hand2", command=self.uninstall_bot,
                                       highlightbackground=RED, highlightthickness=1,
                                       width=12)
        self.btn_uninstall.pack(side="left", padx=4, ipady=4)

        self.log_label = tk.Label(self, text="", bg=BG, fg="#666",
                                  font=("Segoe UI", 8))
        self.log_label.pack(fill="x", padx=10)

        self.update_install_status()
        self.check_status()

    def start_bot(self):
        pid = find_bot_pid()
        if pid:
            return
        if is_installed():
            exe = INSTALLED_BOT
            cwd = INSTALL_DIR
        else:
            exe = BOT_EXE
            cwd = BASE_DIR
        if not os.path.exists(exe):
            self.log_label.configure(text="Registry.exe не найден!")
            return
        subprocess.Popen(
            [exe],
            cwd=cwd,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.after(1500, self.check_status)

    def install_bot(self):
        install_bot()
        self.update_install_status()
        self.log_label.configure(text=f"Установлено в {INSTALL_DIR}")

    def uninstall_bot(self):
        stop_bot()
        remove_autorun()
        if os.path.exists(INSTALL_DIR):
            shutil.rmtree(INSTALL_DIR, ignore_errors=True)
        self.update_install_status()
        self.log_label.configure(text="Удалено")

    def update_install_status(self):
        if is_installed():
            self.btn_install.configure(state="disabled")
            self.btn_uninstall.configure(state="normal")
        else:
            self.btn_install.configure(state="normal")
            self.btn_uninstall.configure(state="disabled")

    def stop_bot(self):
        stop_bot()
        self.update_status("Остановлен", RED)
        self.log_label.configure(text="")

    def check_status(self):
        pid = find_bot_pid()
        if pid:
            self.update_status("Запущен", GREEN)
            self.log_label.configure(text=f"PID: {pid}")
        else:
            self.update_status("Остановлен", RED)
            self.log_label.configure(text="")
        self._check_id = self.after(3000, self.check_status)

    def update_status(self, text, color):
        self.status_label.configure(text=text, fg=color)

    def on_close(self):
        if self._check_id:
            self.after_cancel(self._check_id)
        self.destroy()


if __name__ == "__main__":
    app = BotLauncher()
    app.mainloop()
