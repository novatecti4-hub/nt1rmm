"""
modules/inventory.py — Coleta de inventário enterprise

Coleta completa de hardware e segurança:
  CPU, RAM (slots/tipo/velocidade), GPU, discos (modelo/SSD/HDD),
  redes (MAC/IP/velocidade), BIOS, número de série, domínio AD,
  tipo de máquina (Desktop/Notebook/Servidor/VM), antivírus,
  firewall, BitLocker, atualizações pendentes, software instalado.
"""
import platform, psutil, subprocess, logging, socket, json
log = logging.getLogger("inventory")


class InventoryModule:
    def __init__(self, api, agent_id: str):
        self.api      = api
        self.agent_id = agent_id

    def run(self):
        try:
            payload = self._coletar()
            log.info(
                f"Inventory payload: {payload.get('processador','?')} | "
                f"RAM {payload.get('ram_total_mb',0)}MB | "
                f"{len(payload.get('software', []))} softwares"
            )
            self.api.post("agent-inventory", payload)
            log.info("Inventário enviado com sucesso")
        except Exception as e:
            log.error(f"Inventory erro: {e}", exc_info=True)

    # ──────────────────────────────────────────────
    # Coleta principal
    # ──────────────────────────────────────────────
    def _coletar(self) -> dict:
        is_win = platform.system() == "Windows"
        return {
            "agent_id":               self.agent_id,
            "hostname":               socket.gethostname(),
            "arquitetura":            platform.machine(),
            "fabricante":             self._get_fabricante(),
            "modelo":                 self._get_modelo(),
            "tipo_maquina":           self._get_tipo_maquina(),
            "numero_serie":           self._get_numero_serie(),
            "processador":            self._get_cpu(),
            "cpu_nucleos":            psutil.cpu_count(logical=False) or 0,
            "cpu_threads":            psutil.cpu_count(logical=True)  or 0,
            "cpu_mhz":                self._get_cpu_mhz(),
            "ram_total_mb":           self._get_ram(),
            "ram_slots":              self._get_ram_slots() if is_win else [],
            "gpus":                   self._get_gpus()      if is_win else [],
            "discos":                 self._get_discos(),
            "redes":                  self._get_redes(),
            "bios_fabricante":        self._get_bios("fabricante"),
            "bios_versao":            self._get_bios("versao"),
            "bios_data":              self._get_bios("data"),
            "dominio_ad":             self._get_dominio()   if is_win else None,
            "ultimo_boot":            self._get_ultimo_boot(),
            "antivirus":              self._get_antivirus() if is_win else [],
            "firewall_ativo":         self._get_firewall()  if is_win else None,
            "bitlocker_ativo":        self._get_bitlocker() if is_win else None,
            "atualizacoes_pendentes": self._get_updates()   if is_win else None,
            "software":               self._get_software(),
        }

    # ──────────────────────────────────────────────
    # Hardware básico
    # ──────────────────────────────────────────────
    def _get_fabricante(self) -> str:
        return self._wmic("computersystem get Manufacturer") or "Desconhecido"

    def _get_modelo(self) -> str:
        return self._wmic("computersystem get Model") or "Desconhecido"

    def _get_numero_serie(self) -> str:
        return self._wmic("bios get SerialNumber") or "Desconhecido"

    def _get_tipo_maquina(self) -> str:
        fab = self._get_fabricante().lower()
        mod = self._get_modelo().lower()
        for vm_str in ("vmware", "virtualbox", "virtual machine", "hyper-v", "kvm", "xen", "qemu"):
            if vm_str in fab or vm_str in mod:
                return "VM"
        chassis = self._wmic("systemenclosure get ChassisTypes").lower()
        if any(x in chassis for x in ("8", "9", "10", "11", "14")):
            return "Notebook"
        if any(x in mod for x in ("poweredge", "proliant", "system x", "thinkserver")):
            return "Servidor"
        return "Desktop"

    def _get_cpu(self) -> str:
        if platform.system() == "Windows":
            return self._wmic("cpu get Name") or platform.processor()
        return platform.processor() or "Desconhecido"

    def _get_cpu_mhz(self) -> int:
        try:
            freq = psutil.cpu_freq()
            return int(freq.current) if freq else 0
        except Exception:
            return 0

    def _get_ram(self) -> int:
        return round(psutil.virtual_memory().total / 1024 / 1024)

    # ──────────────────────────────────────────────
    # RAM slots
    # ──────────────────────────────────────────────
    def _get_ram_slots(self) -> list:
        slots = []
        try:
            out = subprocess.check_output(
                ["wmic", "memorychip", "get",
                 "BankLabel,Capacity,Speed,SMBIOSMemoryType", "/format:csv"],
                timeout=15, text=True, stderr=subprocess.DEVNULL
            )
            for line in out.splitlines():
                cols = [c.strip() for c in line.split(",")]
                if len(cols) < 5 or not cols[2]:
                    continue
                try:
                    slots.append({
                        "slot":            cols[1],
                        "capacidade_gb":   round(int(cols[2]) / 1073741824, 1),
                        "tipo":            self._ddr_type(cols[4]),
                        "velocidade_mhz":  int(cols[3]) if cols[3].isdigit() else 0,
                    })
                except Exception:
                    pass
        except Exception:
            pass
        return slots

    @staticmethod
    def _ddr_type(code: str) -> str:
        try:
            return {20:"DDR",21:"DDR2",22:"DDR2 FB",24:"DDR3",
                    26:"DDR4",34:"DDR5"}.get(int(code), "Desconhecido")
        except Exception:
            return "Desconhecido"

    # ──────────────────────────────────────────────
    # GPUs
    # ──────────────────────────────────────────────
    def _get_gpus(self) -> list:
        gpus = []
        try:
            out = subprocess.check_output(
                ["wmic", "path", "win32_videocontroller", "get",
                 "Name,AdapterRAM,DriverVersion", "/format:csv"],
                timeout=15, text=True, stderr=subprocess.DEVNULL
            )
            for line in out.splitlines():
                cols = [c.strip() for c in line.split(",")]
                if len(cols) < 3 or not cols[2]:
                    continue
                try:
                    vram = round(int(cols[1]) / 1048576) if cols[1].isdigit() else 0
                    gpus.append({
                        "nome":    cols[2],
                        "vram_mb": vram,
                        "driver":  cols[3] if len(cols) > 3 else "",
                    })
                except Exception:
                    pass
        except Exception:
            pass
        return gpus

    # ──────────────────────────────────────────────
    # Discos
    # ──────────────────────────────────────────────
    def _get_discos(self) -> list:
        discos = []
        modelos = self._get_disk_models()
        for p in psutil.disk_partitions(all=False):
            try:
                u  = psutil.disk_usage(p.mountpoint)
                mod = modelos.get(p.device.replace("\\\\.\\", ""), "")
                discos.append({
                    "device":      p.device,
                    "mountpoint":  p.mountpoint,
                    "fstype":      p.fstype,
                    "total_gb":    round(u.total / 1e9, 1),
                    "usado_gb":    round(u.used  / 1e9, 1),
                    "livre_gb":    round(u.free  / 1e9, 1),
                    "uso_pct":     round(u.percent, 1),
                    "modelo":      mod,
                    "tipo":        self._tipo_disco(mod),
                })
            except (PermissionError, OSError):
                pass
        return discos

    def _get_disk_models(self) -> dict:
        result = {}
        try:
            out = subprocess.check_output(
                ["wmic", "diskdrive", "get", "DeviceID,Model", "/format:csv"],
                timeout=15, text=True, stderr=subprocess.DEVNULL
            )
            for line in out.splitlines():
                cols = [c.strip() for c in line.split(",")]
                if len(cols) >= 3 and cols[1]:
                    result[cols[1].replace("\\\\.\\", "")] = cols[2]
        except Exception:
            pass
        return result

    @staticmethod
    def _tipo_disco(modelo: str) -> str:
        m = modelo.lower()
        if any(x in m for x in ("ssd", "nvme", "solid", "m.2")):
            return "SSD"
        if any(x in m for x in ("hdd", "7200", "5400")):
            return "HDD"
        return "Desconhecido"

    # ──────────────────────────────────────────────
    # Redes
    # ──────────────────────────────────────────────
    def _get_redes(self) -> list:
        redes  = []
        stats  = psutil.net_if_stats()
        addrs  = psutil.net_if_addrs()
        for iface, addr_list in addrs.items():
            mac = ip = ""
            for a in addr_list:
                if a.family.name in ("AF_LINK", "AF_PACKET") and a.address:
                    mac = a.address
                if a.family.name == "AF_INET" and a.address:
                    ip = a.address
            if not mac:
                continue
            stat = stats.get(iface)
            redes.append({
                "interface":      iface,
                "mac":            mac,
                "ip":             ip,
                "velocidade_mbps": stat.speed if stat else 0,
                "ativo":          stat.isup if stat else False,
            })
        return redes

    # ──────────────────────────────────────────────
    # BIOS
    # ──────────────────────────────────────────────
    def _get_bios(self, campo: str) -> str:
        if platform.system() != "Windows":
            return ""
        mapa = {
            "fabricante": "bios get Manufacturer",
            "versao":     "bios get SMBIOSBIOSVersion",
            "data":       "bios get ReleaseDate",
        }
        return self._wmic(mapa.get(campo, "")) or ""

    # ──────────────────────────────────────────────
    # Domínio AD
    # ──────────────────────────────────────────────
    def _get_dominio(self) -> str:
        dom = self._wmic("computersystem get Domain")
        if dom and dom.lower() not in ("workgroup", ""):
            return dom
        return None

    # ──────────────────────────────────────────────
    # Último boot
    # ──────────────────────────────────────────────
    def _get_ultimo_boot(self) -> str:
        try:
            from datetime import datetime, timezone
            return datetime.fromtimestamp(
                psutil.boot_time(), tz=timezone.utc
            ).isoformat()
        except Exception:
            return ""

    # ──────────────────────────────────────────────
    # Segurança — Antivírus
    # ──────────────────────────────────────────────
    def _get_antivirus(self) -> list:
        avs = []
        try:
            out = subprocess.check_output(
                ["powershell", "-NonInteractive",
                 "Get-CimInstance -Namespace root/SecurityCenter2 "
                 "-ClassName AntiVirusProduct | "
                 "Select-Object displayName,productState | "
                 "ConvertTo-Json -Depth 1 -Compress"],
                timeout=15, text=True, stderr=subprocess.DEVNULL
            )
            items = json.loads(out) if out.strip() else []
            if isinstance(items, dict):
                items = [items]
            for item in items:
                state = item.get("productState", 0)
                avs.append({
                    "nome":       item.get("displayName", ""),
                    "ativo":      bool((state >> 4)  & 0xF),
                    "atualizado": bool((state >> 12) & 0xF == 0),
                })
        except Exception:
            pass
        return avs

    # ──────────────────────────────────────────────
    # Segurança — Firewall
    # ──────────────────────────────────────────────
    def _get_firewall(self) -> bool:
        try:
            out = subprocess.check_output(
                ["powershell", "-NonInteractive",
                 "(Get-NetFirewallProfile | Where-Object {$_.Enabled -eq $true}).Count -gt 0"],
                timeout=10, text=True, stderr=subprocess.DEVNULL
            )
            return "True" in out
        except Exception:
            return None

    # ──────────────────────────────────────────────
    # Segurança — BitLocker
    # ──────────────────────────────────────────────
    def _get_bitlocker(self) -> bool:
        try:
            out = subprocess.check_output(
                ["powershell", "-NonInteractive",
                 "manage-bde -status C: 2>$null | Select-String 'Protection Status'"],
                timeout=15, text=True, stderr=subprocess.DEVNULL
            )
            return "Protection On" in out
        except Exception:
            return None

    # ──────────────────────────────────────────────
    # Segurança — Atualizações pendentes
    # ──────────────────────────────────────────────
    def _get_updates(self) -> int:
        try:
            out = subprocess.check_output(
                ["powershell", "-NonInteractive",
                 "$s=$sess=New-Object -ComObject Microsoft.Update.Session;"
                 "$r=$s.CreateUpdateSearcher().Search('IsInstalled=0 and IsHidden=0');"
                 "$r.Updates.Count"],
                timeout=30, text=True, stderr=subprocess.DEVNULL
            )
            val = out.strip()
            return int(val) if val.isdigit() else 0
        except Exception:
            return None

    # ──────────────────────────────────────────────
    # Software instalado
    # ──────────────────────────────────────────────
    def _get_software(self) -> list:
        try:
            if platform.system() == "Windows":
                return self._get_software_windows()
            elif platform.system() == "Linux":
                return self._get_software_linux()
        except Exception as e:
            log.error(f"Erro ao coletar software: {e}")
        return []

    def _get_software_windows(self) -> list:
        softwares, seen = [], set()
        reg_keys = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        ]
        try:
            import winreg
            for reg_key in reg_keys:
                try:
                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_key)
                except Exception:
                    continue
                for i in range(winreg.QueryInfoKey(key)[0]):
                    sub = None
                    try:
                        sub = winreg.OpenKey(key, winreg.EnumKey(key, i))
                        nome = winreg.QueryValueEx(sub, "DisplayName")[0].strip()
                        if not nome or nome.lower() in seen:
                            continue
                        seen.add(nome.lower())
                        versao = fab = data = None
                        try: versao = winreg.QueryValueEx(sub, "DisplayVersion")[0]
                        except Exception: pass
                        try: fab = winreg.QueryValueEx(sub, "Publisher")[0]
                        except Exception: pass
                        try:
                            d = winreg.QueryValueEx(sub, "InstallDate")[0]
                            if d and len(d) == 8:
                                data = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
                        except Exception:
                            pass
                        softwares.append({"nome": nome, "versao": versao,
                                          "fabricante": fab, "instalado_em": data})
                    except Exception:
                        pass
                    finally:
                        if sub:
                            try: winreg.CloseKey(sub)
                            except Exception: pass
                winreg.CloseKey(key)
        except ImportError:
            pass
        return softwares

    def _get_software_linux(self) -> list:
        softwares = []
        for cmd in (
            ["dpkg-query", "-W", "-f=${Package}\t${Version}\t${Maintainer}\n"],
            ["rpm", "-qa", "--queryformat", "%{NAME}\t%{VERSION}\t%{VENDOR}\n"],
        ):
            try:
                out = subprocess.check_output(cmd, timeout=30, text=True,
                                               stderr=subprocess.DEVNULL)
                for line in out.splitlines():
                    p = line.split("\t")
                    if p[0].strip():
                        softwares.append({
                            "nome":       p[0].strip(),
                            "versao":     p[1].strip() if len(p) > 1 else None,
                            "fabricante": p[2].strip() if len(p) > 2 else None,
                            "instalado_em": None,
                        })
                if softwares:
                    return softwares
            except Exception:
                pass
        return softwares

    # ──────────────────────────────────────────────
    # Helper wmic
    # ──────────────────────────────────────────────
    def _wmic(self, cmd: str) -> str:
        try:
            parts = ["wmic"] + cmd.split()
            if "/value" not in parts:
                parts += ["/value"]
            out = subprocess.check_output(
                parts, timeout=12, text=True, stderr=subprocess.DEVNULL
            )
            for line in out.splitlines():
                if "=" in line:
                    val = line.split("=", 1)[1].strip()
                    if val:
                        return val
        except Exception:
            pass
        return ""
