import platform, socket, logging
log = logging.getLogger("heartbeat")

class HeartbeatModule:
    def __init__(self, api, rustdesk=None):
        self.api = api
        self.rustdesk = rustdesk
        self._rustdesk_id = None

    def run(self):
        # Obter RustDesk ID (só na primeira vez ou se ainda não tem)
        if self.rustdesk and not self._rustdesk_id:
            self._rustdesk_id = self.rustdesk.run()

        payload = {
            "hostname": socket.gethostname(),
            "os_tipo": platform.system(),
            "os_versao": platform.version(),
            "os_arquitetura": platform.machine(),
            "ip_local": socket.gethostbyname(socket.gethostname()),
        }

        if self._rustdesk_id:
            payload["rustdesk_id"] = self._rustdesk_id

        self.api.post("agent-checkin", payload)
