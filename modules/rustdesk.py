import subprocess, logging, time, platform
from pathlib import Path

log = logging.getLogger("rustdesk")

RUSTDESK_EXE_WINDOWS = r"C:\Program Files\RustDesk\rustdesk.exe"
RUSTDESK_PATHS_LINUX = [
    "/usr/share/rustdesk/rustdesk",
    "/usr/bin/rustdesk",
    "/usr/local/bin/rustdesk",
    "/opt/rustdesk/rustdesk",
    "/snap/bin/rustdesk",
]


def _get_exe() -> str:
    if platform.system() == "Windows":
        return RUSTDESK_EXE_WINDOWS
    for path in RUSTDESK_PATHS_LINUX:
        if Path(path).exists():
            return path
    return ""


class RustDeskModule:
    def __init__(self, api, **kwargs):
        self.api = api

    def get_id(self) -> str:
        exe = _get_exe()
        if not exe or not Path(exe).exists():
            log.info("RustDesk não instalado — aguardando instalação manual")
            return ""

        rustdesk_id = self._cmd(exe, "--get-id")

        if not rustdesk_id:
            log.warning("RustDesk instalado mas ID vazio — serviço pode estar iniciando")
            time.sleep(5)
            rustdesk_id = self._cmd(exe, "--get-id")

        rustdesk_id = rustdesk_id.strip()
        if rustdesk_id:
            log.info(f"RustDesk ID: {rustdesk_id}")
        return rustdesk_id

    def _cmd(self, exe, *args) -> str:
        try:
            r = subprocess.run(
                [exe, *args],
                capture_output=True, text=True, timeout=10
            )
            return (r.stdout or "").strip()
        except Exception as e:
            log.error(f"Erro rustdesk {args}: {e}")
            return ""
