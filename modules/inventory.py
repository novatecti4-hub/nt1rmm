import platform, socket, logging, subprocess, json, os
from pathlib import Path

log = logging.getLogger("inventory")


class InventoryModule:
    def __init__(self, api):
        self.api = api

    def run(self):
        data = self._coletar()
        self.api.post("agent-inventory", data)
        log.info("Inventário enviado")

    def _coletar(self) -> dict:
        return {
            "hostname":      socket.gethostname(),
            "os_tipo":       platform.system(),
            "os_versao":     self._os_versao(),
            "os_arquitetura": platform.machine(),
            "processador":   self._processador(),
            "ram_total_mb":  self._ram_total(),
            "fabricante":    self._wmi("Win32_ComputerSystem", "Manufacturer"),
            "modelo":        self._wmi("Win32_ComputerSystem", "Model"),
            "numero_serie":  self._wmi("Win32_BIOS", "SerialNumber"),
            "bios_versao":   self._wmi("Win32_BIOS", "SMBIOSBIOSVersion"),
            "discos":        self._discos(),
            "placas_rede":   self._placas_rede(),
            "softwares":     self._softwares(),
        }

    # ------------------------------------------------------------------
    # Processador — nome real via Registro do Windows
    # ------------------------------------------------------------------
    def _processador(self) -> str:
        if platform.system() == "Windows":
            try:
                import winreg
                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
                )
                name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
                winreg.CloseKey(key)
                return name.strip()
            except Exception:
                pass
            return self._wmi("Win32_Processor", "Name") or platform.processor()
        return platform.processor()

    # ------------------------------------------------------------------
    # Discos — nome real via PowerShell (Get-PhysicalDisk)
    # ------------------------------------------------------------------
    def _discos(self) -> list:
        if platform.system() != "Windows":
            return self._discos_psutil()

        script = """
$result = @()
Get-PhysicalDisk | ForEach-Object {
    $disk = $_
    $vols = ""
    try {
        $parts = Get-Partition -DiskNumber $disk.DeviceId -EA SilentlyContinue
        if ($parts) {
            $vols = ($parts | Get-Volume -EA SilentlyContinue |
                     Where-Object {$_.DriveLetter} |
                     ForEach-Object {"$($_.DriveLetter):"}) -join ","
        }
    } catch {}
    $result += [PSCustomObject]@{
        nome       = $disk.FriendlyName
        tamanho_gb = [math]::Round($disk.Size / 1GB, 1)
        tipo       = $disk.MediaType
        serial     = $disk.SerialNumber
        volumes    = $vols
    }
}
$result | ConvertTo-Json -Compress
"""
        try:
            r = self._ps(script)
            if not r:
                return self._discos_psutil()
            items = json.loads(r)
            if isinstance(items, dict):
                items = [items]
            # Adicionar uso por volume
            return [self._enriquecer_disco(d) for d in items]
        except Exception as e:
            log.warning(f"Discos WMI falhou: {e}")
            return self._discos_psutil()

    def _enriquecer_disco(self, disco: dict) -> dict:
        """Adiciona usado_gb e uso_pct lendo o volume"""
        import psutil
        volumes = disco.get("volumes", "")
        if volumes:
            letra = volumes.split(",")[0].strip()
            try:
                u = psutil.disk_usage(letra)
                disco["usado_gb"]  = round(u.used / 1e9, 1)
                disco["livre_gb"]  = round(u.free / 1e9, 1)
                disco["uso_pct"]   = round(u.percent, 1)
            except Exception:
                pass
        return disco

    def _discos_psutil(self) -> list:
        import psutil
        result = []
        for p in psutil.disk_partitions(all=False):
            try:
                u = psutil.disk_usage(p.mountpoint)
                result.append({
                    "nome":       p.device,
                    "tamanho_gb": round(u.total / 1e9, 1),
                    "usado_gb":   round(u.used  / 1e9, 1),
                    "livre_gb":   round(u.free  / 1e9, 1),
                    "uso_pct":    round(u.percent, 1),
                    "tipo":       p.fstype,
                    "volumes":    p.mountpoint,
                })
            except PermissionError:
                pass
        return result

    # ------------------------------------------------------------------
    # Placas de rede — nome real + MAC + IP
    # ------------------------------------------------------------------
    def _placas_rede(self) -> list:
        if platform.system() != "Windows":
            return self._placas_rede_psutil()

        script = """
$result = @()
Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | ForEach-Object {
    $ip = (Get-NetIPAddress -InterfaceIndex $_.InterfaceIndex `
           -AddressFamily IPv4 -EA SilentlyContinue | Select-Object -First 1).IPAddress
    $result += [PSCustomObject]@{
        nome            = $_.InterfaceDescription
        mac             = $_.MacAddress
        ip              = $ip
        velocidade_mbps = [math]::Round($_.LinkSpeed / 1MB, 0)
    }
}
$result | ConvertTo-Json -Compress
"""
        try:
            r = self._ps(script)
            if not r:
                return self._placas_rede_psutil()
            items = json.loads(r)
            if isinstance(items, dict):
                items = [items]
            return items
        except Exception as e:
            log.warning(f"Placas rede falhou: {e}")
            return self._placas_rede_psutil()

    def _placas_rede_psutil(self) -> list:
        import psutil
        result = []
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        for nome, endericos in addrs.items():
            if nome not in stats or not stats[nome].isup:
                continue
            mac = ip = ""
            for e in endericos:
                if e.family.name in ("AF_LINK", "AF_PACKET"):
                    mac = e.address
                if e.family.name == "AF_INET":
                    ip = e.address
            result.append({"nome": nome, "mac": mac, "ip": ip})
        return result

    # ------------------------------------------------------------------
    # Softwares instalados
    # ------------------------------------------------------------------
    def _softwares(self) -> list:
        if platform.system() != "Windows":
            return []

        script = """
$paths = @(
    "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*",
    "HKLM:\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*"
)
Get-ItemProperty $paths -EA SilentlyContinue |
    Where-Object { $_.DisplayName -and $_.DisplayName.Trim() -ne "" } |
    Select-Object DisplayName, DisplayVersion, Publisher, InstallDate |
    Sort-Object DisplayName |
    ConvertTo-Json -Compress
"""
        try:
            r = self._ps(script)
            if not r:
                return []
            items = json.loads(r)
            if isinstance(items, dict):
                items = [items]
            return [
                {
                    "nome":         i.get("DisplayName", ""),
                    "versao":       i.get("DisplayVersion", ""),
                    "fabricante":   i.get("Publisher", ""),
                    "instalado_em": i.get("InstallDate", ""),
                }
                for i in items if i.get("DisplayName")
            ]
        except Exception as e:
            log.warning(f"Softwares falhou: {e}")
            return []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _wmi(self, classe: str, campo: str) -> str:
        script = f"(Get-WmiObject {classe} | Select-Object -First 1).{campo}"
        return (self._ps(script) or "").strip()

    def _ps(self, script: str, timeout: int = 30) -> str:
        try:
            r = subprocess.run(
                ["powershell", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                 "-Command", script],
                capture_output=True, text=True, timeout=timeout
            )
            return (r.stdout or "").strip()
        except Exception as e:
            log.error(f"PowerShell erro: {e}")
            return ""

    def _os_versao(self) -> str:
        if platform.system() == "Windows":
            return self._wmi("Win32_OperatingSystem", "Caption")
        return platform.version()

    def _ram_total(self) -> int:
        import psutil
        return int(psutil.virtual_memory().total / 1_000_000)
