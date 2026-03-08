import platform, socket, logging
import psutil
log = logging.getLogger("inventory")

class InventoryModule:
    def __init__(self, api):
        self.api = api

    def run(self):
        hardware = {
            "fabricante": "Desconhecido",
            "modelo": platform.node(),
            "numero_serie": "",
            "processador": platform.processor(),
            "ram_total_mb": psutil.virtual_memory().total // 1_000_000,
            "discos_json": self._discos(),
            "placas_rede_json": self._redes(),
            "bios_versao": ""
        }
        software = self._software()
        self.api.post("agent-inventory", {
            "hardware": hardware,
            "software": software
        })

    def _discos(self):
        discos = []
        for p in psutil.disk_partitions(all=False):
            try:
                u = psutil.disk_usage(p.mountpoint)
                discos.append({
                    "device": p.device,
                    "mountpoint": p.mountpoint,
                    "total_gb": round(u.total / 1e9, 1)
                })
            except Exception:
                pass
        return discos

    def _redes(self):
        redes = []
        for nome, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family.name in ("AF_INET", "AF_INET6"):
                    redes.append({"interface": nome, "ip": addr.address})
                    break
        return redes

    def _software(self):
        software = []
        if platform.system() == "Windows":
            try:
                import winreg
                for hive in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
                    for path in [
                        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
                    ]:
                        try:
                            key = winreg.OpenKey(hive, path)
                            for i in range(winreg.QueryInfoKey(key)[0]):
                                try:
                                    sub = winreg.OpenKey(key, winreg.EnumKey(key, i))
                                    nome = winreg.QueryValueEx(sub, "DisplayName")[0]
                                    versao = ""
                                    try:
                                        versao = winreg.QueryValueEx(sub, "DisplayVersion")[0]
                                    except Exception:
                                        pass
                                    if nome:
                                        software.append({"nome": nome, "versao": versao,
                                                         "fabricante": "", "instalado_em": None})
                                except Exception:
                                    pass
                        except Exception:
                            pass
            except Exception:
                pass
        return software[:200]  # limite de 200 programas
