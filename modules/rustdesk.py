import subprocess, logging, time
from pathlib import Path

log = logging.getLogger("rustdesk")

RUSTDESK_EXE = r"C:\Program Files\RustDesk\rustdesk.exe"


class RustDeskModule:
    def __init__(self, api, **kwargs):
        self.api = api

    def get_id(self) -> str:
        if not Path(RUSTDESK_EXE).exists():
            log.info("RustDesk não instalado — aguardando instalação manual")
            return ""

        rustdesk_id = self._cmd("--get-id")

        if not rustdesk_id:
            log.warning("RustDesk instalado mas ID vazio — serviço pode estar iniciando")
            time.sleep(5)
            rustdesk_id = self._cmd("--get-id")

        rustdesk_id = rustdesk_id.strip()
        if rustdesk_id:
            log.info(f"RustDesk ID: {rustdesk_id}")
        return rustdesk_id

    def _cmd(self, *args) -> str:
        try:
            r = subprocess.run(
                [RUSTDESK_EXE, *args],
                capture_output=True, text=True, timeout=10
            )
            return (r.stdout or "").strip()
        except Exception as e:
            log.error(f"Erro rustdesk {args}: {e}")
            return ""
