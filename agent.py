#!/usr/bin/env python3
import time, threading, signal, sys, logging, platform, os
from pathlib import Path

if platform.system() == "Windows":
    LOG_DIR = Path(r"C:\ProgramData\NVCloud")
else:
    LOG_DIR = Path("/var/log/nvcloud")

LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "nvcloud-agent.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(str(LOG_FILE), encoding="utf-8")
    ]
)
log = logging.getLogger("agent")

from config import Config
from utils.api import ApiClient
from modules.heartbeat import HeartbeatModule
from modules.metrics import MetricsModule
from modules.inventory import InventoryModule
from modules.commands import CommandsModule
from modules.ailocal import LocalAIAnalyzer
from modules.shield import ShieldModule
from modules.rustdesk import RustDeskModule
from tray import TrayApp


def _tem_interface() -> bool:
    """False quando rodando como serviço Windows (sem desktop)"""
    try:
        session = os.environ.get("SESSIONNAME", "")
        if session in ("", "Services"):
            return False
        import ctypes
        return ctypes.windll.user32.GetForegroundWindow() != 0
    except:
        return False


def _instalar_servico():
    import subprocess, os
    exe_path = os.path.abspath(sys.argv[0])
    subprocess.run([
        "sc", "create", "NVCloudAgent",
        "binPath=", f'"{exe_path}"',
        "start=", "auto",
        "DisplayName=", "NVCloud Agent"
    ])
    subprocess.run([
        "sc", "description", "NVCloudAgent",
        "Agente de monitoramento NVCloud RMM"
    ])
    subprocess.run(["sc", "start", "NVCloudAgent"])
    _instalar_tray_startup()
    print("NVCloud Agent instalado, servico iniciado e tray registrado!")


def _desinstalar_servico():
    import subprocess
    subprocess.run(["sc", "stop",   "NVCloudAgent"], capture_output=True)
    subprocess.run(["sc", "delete", "NVCloudAgent"])
    _remover_tray_startup()
    print("NVCloud Agent removido!")


def _instalar_tray_startup():
    import winreg, os
    exe_path = os.path.abspath(sys.argv[0])
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, "NVCloudAgentTray", 0, winreg.REG_SZ,
                          f'"{exe_path}" --tray')
        winreg.CloseKey(key)
        log.info("Tray registrado no startup do Windows")
    except Exception as e:
        log.error(f"Erro ao registrar tray startup: {e}")


def _remover_tray_startup():
    import winreg
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE
        )
        winreg.DeleteValue(key, "NVCloudAgentTray")
        winreg.CloseKey(key)
        log.info("Tray removido do startup")
    except Exception:
        pass


class NVCloudAgent:
    def __init__(self):
        self.cfg       = Config()
        self.api       = ApiClient(self.cfg.supabase_url, self.cfg.token)
        self.running   = True
        self.ai        = LocalAIAnalyzer()
        self.rustdesk  = RustDeskModule(self.api)
        self.heartbeat = HeartbeatModule(self.api, self.rustdesk)
        self.metrics   = MetricsModule(self.api, self.ai)
        self.inventory = InventoryModule(self.api)
        self.commands  = CommandsModule(self.api)
        self.shield    = ShieldModule(self.api, self.cfg.token, self.cfg.app_url)
        self.tray      = TrayApp(self)

    def _loop(self, mod, interval: int, name: str):
        while self.running:
            try:
                mod.run()
            except Exception as e:
                log.error(f"{name}: {e}", exc_info=True)
            time.sleep(interval)

    def start(self):
        log.info("NVCloud Agent iniciando...")
        signal.signal(signal.SIGTERM, lambda *_: self.stop())
        signal.signal(signal.SIGINT,  lambda *_: self.stop())

        # Tray só quando há interface gráfica (não roda como serviço)
        if _tem_interface():
            try:
                self.tray.iniciar()
                log.info("Tray iniciado")
            except Exception as e:
                log.warning(f"Tray não iniciado: {e}")

        threads = [
            threading.Thread(target=self._loop, args=(self.heartbeat, 60,    "heartbeat"), daemon=True),
            threading.Thread(target=self._loop, args=(self.metrics,   300,   "metrics"),   daemon=True),
            threading.Thread(target=self._loop, args=(self.inventory, 86400, "inventory"), daemon=True),
            threading.Thread(target=self._loop, args=(self.commands,  30,    "commands"),  daemon=True),
            threading.Thread(target=self._loop, args=(self.shield,    1800,  "shield"),    daemon=True),
        ]
        for t in threads:
            t.start()

        log.info(f"Agente iniciado — {len(threads)} módulos ativos.")
        log.info(f"Log em: {LOG_FILE}")

        # Inventário imediato na primeira execução
        try:
            self.inventory.run()
        except Exception as e:
            log.error(f"Inventário inicial: {e}")

        while self.running:
            time.sleep(1)

    def stop(self):
        log.info("Encerrando...")
        self.running = False
        sys.exit(0)


if __name__ == "__main__":
    if "--install" in sys.argv:
        _instalar_servico()

    elif "--uninstall" in sys.argv:
        _desinstalar_servico()

    elif "--tray" in sys.argv:
        # Modo só ícone na bandeja — iniciado pelo startup do Windows após login
        cfg = Config()

        class FakeAgent:
            pass

        fa      = FakeAgent()
        fa.cfg  = cfg
        fa.stop = lambda: sys.exit(0)

        tray = TrayApp(fa)
        try:
            tray.iniciar()
        except Exception as e:
            log.error(f"Tray erro: {e}")

        while True:
            time.sleep(1)

    else:
        NVCloudAgent().start()
