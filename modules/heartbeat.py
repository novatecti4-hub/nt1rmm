import platform, socket, subprocess, logging, psutil
from datetime import datetime, timezone

log = logging.getLogger("heartbeat")


class HeartbeatModule:
    def __init__(self, api, rustdesk, commands=None, agent_id=None):
        self.api      = api
        self.rustdesk = rustdesk
        self.commands = commands
        self.agent_id = agent_id or ""

    def run(self):
        payload = {
            "agent_id":       self.agent_id,
            "hostname":       socket.gethostname(),
            "ip_local":       self._ip(),
            "os_tipo":        platform.system(),         # "Windows" ou "Linux"
            "os_versao":      self._get_os_versao(),     # CORRIGIDO: "Windows 11 Pro 23H2"
            "os_arquitetura": platform.machine(),        # "AMD64", "x86_64", etc.
            "agent_version":  "1.0.0",
            "rustdesk_id":    self.rustdesk.get_id(),
        }
        resp = self.api.post("agent-checkin", payload)

        # Repassa jobs para commands — sem chamar checkin de novo
        if resp and self.commands:
            jobs = resp.get("jobs", [])
            if jobs:
                self.commands.atualizar_jobs(jobs)

        log.info(
            f"Heartbeat OK — "
            f"CPU: {psutil.cpu_percent(interval=0.1):.0f}% | "
            f"RAM: {psutil.virtual_memory().percent:.0f}% | "
            f"OS: {payload['os_versao']} | "
            f"RustDesk: {payload['rustdesk_id'] or 'não instalado'}"
        )

    def _get_os_versao(self) -> str:
        """
        Retorna o nome amigável e completo do sistema operacional.

        Windows → "Windows 11 Pro 23H2"  /  "Windows 10 Pro 22H2"
        Linux   → "Ubuntu 22.04.3 LTS"   /  "Debian GNU/Linux 12 (bookworm)"
        Outro   → "Darwin 23.4.0"
        """
        try:
            if platform.system() == "Windows":
                return self._get_windows_nome()
            elif platform.system() == "Linux":
                return self._get_linux_nome()
            else:
                return f"{platform.system()} {platform.release()}"
        except Exception:
            return f"{platform.system()} {platform.release()}"

    def _get_windows_nome(self) -> str:
        """Pega nome amigável do Windows via WMI + registro."""
        caption = ""
        try:
            # WMI: retorna "Microsoft Windows 11 Pro", "Microsoft Windows 10 Pro", etc.
            out = subprocess.check_output(
                ["wmic", "os", "get", "Caption", "/value"],
                timeout=10, text=True, stderr=subprocess.DEVNULL
            )
            for line in out.splitlines():
                if "Caption=" in line:
                    caption = line.split("=", 1)[1].strip()
                    # Remove prefixo "Microsoft " para ficar mais limpo
                    caption = caption.replace("Microsoft ", "").strip()
                    break
        except Exception:
            pass

        # Tenta obter versão de feature (22H2, 23H2, 24H2, etc.) do registro
        display_version = ""
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
            )
            display_version = winreg.QueryValueEx(key, "DisplayVersion")[0]
            winreg.CloseKey(key)
        except Exception:
            pass

        if caption and display_version:
            return f"{caption} {display_version}"   # "Windows 11 Pro 23H2"
        elif caption:
            return caption                           # "Windows 11 Pro"
        else:
            # Fallback usando platform
            release = platform.release()            # "10" ou "11"
            return f"Windows {release}"

    def _get_linux_nome(self) -> str:
        """Lê /etc/os-release para nome bonito do Linux."""
        try:
            with open("/etc/os-release") as f:
                for line in f:
                    if line.startswith("PRETTY_NAME="):
                        return line.split("=", 1)[1].strip().strip('"')
        except Exception:
            pass
        # Fallback
        return f"Linux {platform.release()}"

    def _ip(self) -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            try:
                return socket.gethostbyname(socket.gethostname())
            except Exception:
                return "0.0.0.0"

    def _uptime(self) -> int:
        try:
            boot = psutil.boot_time()
            now  = datetime.now(timezone.utc).timestamp()
            return int(now - boot)
        except Exception:
            return 0
