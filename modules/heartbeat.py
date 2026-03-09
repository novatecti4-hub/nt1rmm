import platform, socket, logging, psutil
from datetime import datetime, timezone

log = logging.getLogger("heartbeat")


class HeartbeatModule:
    def __init__(self, api, rustdesk, commands=None):  # CORRIGIDO: aceita commands
        self.api      = api
        self.rustdesk = rustdesk
        self.commands = commands

    def run(self):
        payload = {
            "hostname":       socket.gethostname(),
            "ip_local":       self._ip(),               # CORRIGIDO: era "ip"
            "os_tipo":        platform.system(),         # CORRIGIDO: era "os" + release concatenado
            "os_versao":      platform.version(),
            "os_arquitetura": platform.machine(),        # CORRIGIDO: era "arquitetura"
            "agent_version":  "1.0.0",
            "rustdesk_id":    self.rustdesk.get_id(),
        }
        resp = self.api.post("agent-checkin", payload)

        # CORRIGIDO: repassa jobs para commands — sem chamar checkin de novo
        if resp and self.commands:
            jobs = resp.get("jobs", [])
            if jobs:
                self.commands.atualizar_jobs(jobs)

        log.info(
            f"Heartbeat OK — "
            f"CPU: {psutil.cpu_percent(interval=0.1):.0f}% | "
            f"RAM: {psutil.virtual_memory().percent:.0f}% | "
            f"RustDesk: {payload['rustdesk_id'] or 'não instalado'}"
        )

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
