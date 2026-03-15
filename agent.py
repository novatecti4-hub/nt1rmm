#!/usr/bin/env python3
import time, threading, signal, sys, logging, platform, os
from pathlib import Path

if platform.system() == "Windows":
    LOG_DIR = Path(r"C:\ProgramData\NVCloud")
else:
    LOG_DIR = Path("/var/log/nvcloud")

LOG_DIR.mkdir(parents=True, exist_ok=True)

# Serviço usa nvcloud-agent.log, tray usa nvcloud-tray.log — evita conflito de lock
_is_tray = "--tray" in sys.argv
_log_file = LOG_DIR / ("nvcloud-tray.log" if _is_tray else "nvcloud-agent.log")

_handlers = [logging.StreamHandler()]
for _attempt in [_log_file, LOG_DIR / "nvcloud-fallback.log"]:
    try:
        _handlers.append(logging.FileHandler(str(_attempt), encoding="utf-8"))
        break
    except PermissionError:
        continue

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=_handlers
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


def _instalar_tray_startup():
    if platform.system() != "Windows":
        return
    import winreg
    exe_path = os.path.abspath(sys.argv[0])
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, "NVCloudAgentTray", 0, winreg.REG_SZ,
                          f'"{exe_path}" --tray')
        winreg.CloseKey(key)
        log.info("Tray registrado no startup")
    except Exception as e:
        log.error(f"Erro ao registrar tray startup: {e}")


def _remover_tray_startup():
    if platform.system() != "Windows":
        return
    import winreg
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, "NVCloudAgentTray")
        winreg.CloseKey(key)
    except Exception:
        pass


def _instalar_servico():
    import subprocess
    exe_path = os.path.abspath(sys.argv[0])
    subprocess.run(["sc", "create", "NVCloudAgent",
                    "binPath=", f'"{exe_path}"',
                    "start=", "auto",
                    "DisplayName=", "NVCloud Agent"])
    subprocess.run(["sc", "description", "NVCloudAgent",
                    "Agente de monitoramento NVCloud RMM"])
    subprocess.run(["sc", "config", "NVCloudAgent", "start=", "auto"])
    subprocess.run(["sc", "start", "NVCloudAgent"])
    _instalar_tray_startup()
    print("NVCloud Agent instalado e iniciado!")


def _desinstalar_servico():
    import subprocess
    subprocess.run(["sc", "stop",   "NVCloudAgent"], capture_output=True)
    subprocess.run(["sc", "delete", "NVCloudAgent"])
    _remover_tray_startup()
    print("NVCloud Agent removido!")


class NVCloudAgent:
    def __init__(self):
        self.cfg = Config()

        if not self.cfg.agent_id:
            log.error("agent_id não encontrado no config! Execute --install primeiro.")
            sys.exit(1)

        self.api     = ApiClient(self.cfg.supabase_url, self.cfg.token)
        self.running = True
        self.ai      = LocalAIAnalyzer()

        self.commands  = CommandsModule(self.api)
        self.rustdesk  = RustDeskModule(self.api)
        self.heartbeat = HeartbeatModule(self.api, self.rustdesk, self.commands, self.cfg.agent_id)
        self.metrics   = MetricsModule(self.api, self.ai)
        self.inventory = InventoryModule(self.api, self.cfg.agent_id)
        self.shield    = ShieldModule(self.api, self.cfg.token,
                                      self.cfg.app_url, self.cfg.agent_id)
        self.tray      = TrayApp(self)

    def _loop(self, mod, interval: int, name: str):
        while self.running:
            try:
                mod.run()
            except Exception as e:
                log.error(f"{name}: {e}", exc_info=True)
            time.sleep(interval)

    def start(self):
        log.info(f"NVCloud Agent iniciando — agent_id={self.cfg.agent_id}")

        threads = [
            threading.Thread(target=self._loop, args=(self.heartbeat, 60,    "heartbeat"), daemon=True),
            threading.Thread(target=self._loop, args=(self.metrics,   300,   "metrics"),   daemon=True),
            threading.Thread(target=self._loop, args=(self.inventory, 86400, "inventory"), daemon=True),
            threading.Thread(target=self._loop, args=(self.commands,  30,    "commands"),  daemon=True),
            threading.Thread(target=self._loop, args=(self.shield,    1800,  "shield"),    daemon=True),
        ]
        for t in threads:
            t.start()

        log.info(f"Agente iniciado — {len(threads)} módulos ativos")

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


# ── Windows Service via pywin32 ──────────────────────────────────
if platform.system() == "Windows":
    try:
        import win32serviceutil, win32service, win32event, servicemanager

        class NVCloudService(win32serviceutil.ServiceFramework):
            _svc_name_        = "NVCloudAgent"
            _svc_display_name_ = "NVCloud Agent"
            _svc_description_  = "Agente de monitoramento NVCloud RMM"

            def __init__(self, args):
                win32serviceutil.ServiceFramework.__init__(self, args)
                self.stop_event = win32event.CreateEvent(None, 0, 0, None)
                self.agent = None

            def SvcStop(self):
                self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
                win32event.SetEvent(self.stop_event)
                if self.agent:
                    self.agent.running = False

            def SvcDoRun(self):
                servicemanager.LogMsg(
                    servicemanager.EVENTLOG_INFORMATION_TYPE,
                    servicemanager.PYS_SERVICE_STARTED,
                    (self._svc_name_, "")
                )
                self.agent = NVCloudAgent()
                self.agent.start()

        _HAS_WIN32 = True
    except ImportError:
        _HAS_WIN32 = False
else:
    _HAS_WIN32 = False


if __name__ == "__main__":
    if "--install" in sys.argv:
        if _HAS_WIN32:
            win32serviceutil.InstallService(
                NVCloudService,
                NVCloudService._svc_name_,
                NVCloudService._svc_display_name_,
                startType=win32service.SERVICE_AUTO_START
            )
            win32serviceutil.StartService(NVCloudService._svc_name_)
            _instalar_tray_startup()
            print("NVCloud Agent instalado e iniciado!")
        else:
            _instalar_servico()
    elif "--uninstall" in sys.argv:
        if _HAS_WIN32:
            win32serviceutil.StopService(NVCloudService._svc_name_)
            win32serviceutil.RemoveService(NVCloudService._svc_name_)
            _remover_tray_startup()
        else:
            _desinstalar_servico()
    elif "--tray" in sys.argv:
        cfg = Config()
        class FakeAgent:
            pass
        fa      = FakeAgent()
        fa.cfg  = cfg
        fa.stop = lambda: sys.exit(0)
        tray    = TrayApp(fa)
        try:
            tray.iniciar()
        except Exception as e:
            log.error(f"Tray erro: {e}")
        while True:
            time.sleep(1)
    elif _HAS_WIN32 and len(sys.argv) == 1:
        # Iniciado pelo SCM sem argumentos — roda como serviço
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(NVCloudService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        NVCloudAgent().start()
