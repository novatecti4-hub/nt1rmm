import platform, socket, logging
log = logging.getLogger("heartbeat")

class HeartbeatModule:
    def __init__(self, api):
        self.api = api

    def run(self):
        self.api.post("agent-checkin", {
            "hostname": socket.gethostname(),
            "os_tipo": platform.system(),
            "os_versao": platform.version(),
            "os_arquitetura": platform.machine(),
            "ip_local": socket.gethostbyname(socket.gethostname())
        })
