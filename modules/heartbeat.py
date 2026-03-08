import platform, socket, logging, psutil
from datetime import datetime, timezone

log = logging.getLogger("heartbeat")


class HeartbeatModule:
    def __init__(self, api, rustdesk):
        self.api      = api
        self.rustdesk = rustdesk

    def run(self):
        payload = {
            "hostname":    socket.gethostname(),
            "ip":          self._ip(),
            "os":          f"{platform.system()} {platform.release()}",
            "os_versao":   platform.version(),
            "arquitetura": platform.machine(),
            "uptime_s":    self._uptime(),
            "status":      "online",
            "rustdesk_id": self.rustdesk.get_id(),
            "cpu_uso":     psutil.cpu_percent(interval=1),
            "ram_uso_pct": psutil.virtual_memory().percent,
            "coletado_em": datetime.now(timezone.utc).isoformat(),
        }
        self.api.post("agent-checkin", payload)
        log.info(
            f"Heartbeat OK — "
            f"CPU: {payload['cpu_uso']}% | "
            f"RAM: {payload['ram_uso_pct']}% | "
            f"RustDesk: {payload['rustdesk_id'] or 'não instalado'}"
        )

    def _ip(self) -> str:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
            sock.close()
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
