import platform, socket, logging, subprocess, json, os
from pathlib import Path

log = logging.getLogger("inventory")


class InventoryModule:
    def __init__(self, api):
        self.api = api

    def run(self):
        data = self._coletar()
        self.api.post("agent-inventory", data)

    # ------------------------------------------------------------------
    # Coleta completa
    # ------------------------------------------------------------------
    def _coletar(self) -> dict:
        return {
            "hostname":    socket.gethostname(),
            "os_tipo":     platform.system(),
            "os_versao":   self._os_versao(),
            "processador": self._processador(),
            "ram_total_mb": self._ram_total(),
            "fabricante":  self._wmi("Win32_ComputerSystem", "Manufacturer"),
            "modelo":      self._wmi("Win32_ComputerSystem", "Model"),
            "numero_serie":self._wmi("Win32_BIOS",            "SerialNumber"),
            "bios_versao": self._wmi("Win32_BIOS",            "SMBIOSBIOSVersion"),
            "discos":      self._discos(),
            "placas_rede": self._placas_rede(),
            "softwares":   self._softwares(),
        }

    # ------------------------------------------------------------------
    # Processador — Registro do Windows (nome correto ex: Core i5-4450)
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
            # Fallback WMI
            return self._wmi("Win32_Processor", "Name") or platform.processor()
        return platform.processor()

    # ------------------------------------------------------------------
    # Discos — nome real (ex: ADATA SX8200PNP, WD Blue)
    # ------------------------------------------------------------------
    def _discos(self) -> list:
        if platform.system() != "Windows":
            return self._discos_psutil()

        script = """
$discos = @()
Get-PhysicalDisk | ForEach-Object {
    $d = $_
    $part = Get-Partition -DiskNumber $d.DeviceId -ErrorAction SilentlyContinue
    $vols = @()
    if ($part) {
        $vols = ($part | Get-Volume -ErrorAction SilentlyContinue |
                  Where-Object {$_.DriveLetter} |
                  ForEach-Object {"$($_.DriveLetter):"}) -join ","
    }
    $discos += [PSCustomObject]@{
        nome       = $d.FriendlyName
        tamanho_gb = [math]::Round($d.Size / 1GB, 1)
        tipo       = $d.MediaType
        serial     = $d.SerialNumber
        volumes    = $vols
    }
}
$discos | ConvertTo-Json -Compress
"""
        try:
            r = self._ps(script)
            items = json.loads(r)
            if isinstance(items, dict):
                items = [items]
            return items
        except Exception as e:
            log.warning(f"Discos WMI falhou: {e}")
            return self._discos_psutil()

    def _discos_psutil(self) -> list:
        import psutil
        result = []
        for p in psutil.disk_partitions(all=False):
            try:
                u = psutil.disk_usage(p.mountpoint)
                result.append({
                    "nome":       p.device,
                    "tamanho_gb": round(u.total / 1e9, 1),
                    "tipo":       p.fstype,
                    "volumes":    p.mountpoint,
                })
            except PermissionError:
                pass
        return result

    # ------------------------------------------------------------------
    # Placas de rede — nome real
    # ------------------------------------------------------------------
    def _placas_rede(self) -> list:
        if platform.system() != "Windows":
            return []
        script = """
Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | ForEach-Object {
    [PSCustomObject]@{
        nome = $_.InterfaceDescription
        mac  = $_.MacAddress
        velocidade_mbps = [math]::Round($_.LinkSpeed / 1MB, 0)
    }
} | ConvertTo-Json -Compress
"""
        try:
            r = self._ps(script)
            items = json.loads(r)
            if isinstance(items, dict):
                items = [items]
            return items
        except Exception as e:
            log.warning(f"Placas rede falhou: {e}")
            return []

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
Get-ItemProperty $paths -ErrorAction SilentlyContinue |
    Where-Object { $_.DisplayName -and $_.DisplayName.Trim() -ne "" } |
    Select-Object DisplayName, DisplayVersion, Publisher, InstallDate |
    Sort-Object DisplayName |
    ConvertTo-Json -Compress
"""
        try:
            r = self._ps(script)
            items = json.loads(r)
            if isinstance(items, dict):
                items = [items]
            return [
                {
                    "nome":       i.get("DisplayName", ""),
                    "versao":     i.get("DisplayVersion", ""),
                    "fabricante": i.get("Publisher", ""),
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
        return self._ps(script) or ""

    def _ps(self, script: str) -> str:
        try:
            r = subprocess.run(
                ["powershell", "-NonInteractive", "-Command", script],
                capture_output=True, text=True, timeout=30
            )
            return (r.stdout or "").strip()
        except Exception as e:
            log.error(f"PowerShell erro: {e}")
            return ""

    def _os_versao(self) -> str:
        if platform.system() == "Windows":
            return self._ps("(Get-WmiObject Win32_OperatingSystem).Caption").strip()
        return platform.version()

    def _ram_total(self) -> int:
        import psutil
        return int(psutil.virtual_memory().total / 1_000_000)
