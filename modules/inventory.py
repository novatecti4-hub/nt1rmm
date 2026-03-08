import platform, psutil, subprocess, logging, socket
log = logging.getLogger("inventory")


class InventoryModule:
    def __init__(self, api, agent_id: str):
        self.api      = api
        self.agent_id = agent_id

    def run(self):
        try:
            payload = {
                "agent_id":     self.agent_id,
                "fabricante":   self._get_fabricante(),
                "modelo":       self._get_modelo(),
                "processador":  self._get_cpu(),
                "ram_total_mb": self._get_ram(),
                "hostname":     socket.gethostname(),
                "so":           f"{platform.system()} {platform.release()}",
                "arquitetura":  platform.machine(),
            }
            log.info(f"Inventory payload: {payload}")
            self.api.post("agent-inventory", payload)
            log.info("Inventário enviado com sucesso")
        except Exception as e:
            log.error(f"Inventory erro: {e}", exc_info=True)

    def _get_cpu(self) -> str:
        try:
            if platform.system() == "Windows":
                out = subprocess.check_output(
                    ["wmic", "cpu", "get", "Name", "/value"],
                    timeout=10, text=True
                )
                for line in out.splitlines():
                    if "Name=" in line:
                        return line.split("=", 1)[1].strip()
            return platform.processor() or "Desconhecido"
        except Exception:
            return platform.processor() or "Desconhecido"

    def _get_ram(self) -> int:
        try:
            return round(psutil.virtual_memory().total / (1024 * 1024))
        except Exception:
            return 0

    def _get_fabricante(self) -> str:
        try:
            if platform.system() == "Windows":
                out = subprocess.check_output(
                    ["wmic", "computersystem", "get", "Manufacturer", "/value"],
                    timeout=10, text=True
                )
                for line in out.splitlines():
                    if "Manufacturer=" in line:
                        return line.split("=", 1)[1].strip()
        except Exception:
            pass
        return "Desconhecido"

    def _get_modelo(self) -> str:
        try:
            if platform.system() == "Windows":
                out = subprocess.check_output(
                    ["wmic", "computersystem", "get", "Model", "/value"],
                    timeout=10, text=True
                )
                for line in out.splitlines():
                    if "Model=" in line:
                        return line.split("=", 1)[1].strip()
        except Exception:
            pass
        return "Desconhecido"
