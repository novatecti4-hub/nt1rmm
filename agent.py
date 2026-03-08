#!/usr/bin/env python3
import time, threading, signal, sys, logging, os, platform
from pathlib import Path

# Definir pasta de log com permissão de escrita
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

class NVCloudAgent:
    def __init__(self):
        self.cfg = Config()
        self.api = ApiClient(self.cfg.supabase_url, self.cfg.token)
        self.running = True
        self.ai = LocalAIAnalyzer()
        self.heartbeat = HeartbeatModule(self.api)
        self.metrics = MetricsModule(self.api, self.ai)
        self.inventory = InventoryModule(self.api)
        self.commands = CommandsModule(self.api)
        self.shield = ShieldModule(self.api, self.cfg.token, self.cfg.app_url)

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
        signal.signal(signal.SIGINT, lambda *_: self.stop())

        threads = [
            threading.Thread(target=self._loop, args=(self.heartbeat, 60, "heartbeat"), daemon=True),
            threading.Thread(target=self._loop, args=(self.metrics, 300, "metrics"), daemon=True),
            threading.Thread(target=self._loop, args=(self.inventory, 86400, "inventory"), daemon=True),
            threading.Thread(target=self._loop, args=(self.commands, 30, "commands"), daemon=True),
            threading.Thread(target=self._loop, args=(self.shield, 1800, "shield"), daemon=True),
        ]
        for t in threads:
            t.start()

        log.info(f"Agente iniciado — {len(threads)} módulos ativos.")
        log.info(f"Log em: {LOG_FILE}")
        self.inventory.run()

        while self.running:
            time.sleep(1)

    def stop(self):
        log.info("Encerrando...")
        self.running = False
        sys.exit(0)

if __name__ == "__main__":
    NVCloudAgent().start()
