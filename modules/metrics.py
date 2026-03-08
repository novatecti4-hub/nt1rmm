import psutil, platform, logging, subprocess, json, os
from pathlib import Path

log = logging.getLogger("metrics")

LHM_DIR  = Path(r"C:\ProgramData\NVCloud\LHM")
LHM_DLL  = LHM_DIR / "LibreHardwareMonitorLib.dll"
LHM_HID  = LHM_DIR / "HidSharp.dll"
LHM_URL  = "https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases/download/v0.9.4/LibreHardwareMonitor-net472.zip"

# Script PowerShell embutido — retorna temperatura como número puro
_PS_TEMP = r"""
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$DllPath = "{dll}"
$HidPath = "{hid}"
$FinalTemp = 0

try {{
    if (Test-Path $HidPath) {{ [System.Reflection.Assembly]::LoadFile($HidPath) | Out-Null }}
    [System.Reflection.Assembly]::LoadFile($DllPath) | Out-Null
    $c = New-Object LibreHardwareMonitor.Hardware.Computer
    $c.IsCpuEnabled = $true
    $c.IsMotherboardEnabled = $true
    $c.Open()
    for ($i = 0; $i -lt 3; $i++) {{
        foreach ($hw in $c.Hardware) {{ $hw.Update() }}
        Start-Sleep -Milliseconds 200
    }}
    foreach ($hw in $c.Hardware) {{
        $hw.Update()
        if ($hw.HardwareType -match "Cpu|Motherboard|SuperIO") {{
            foreach ($s in $hw.Sensors) {{
                if ($s.SensorType -ne "Temperature") {{ continue }}
                if ($s.Name -match "Distance") {{ continue }}
                if ($s.Value -le 0) {{ continue }}
                $valid = $false
                if ($hw.HardwareType -eq "Cpu") {{ $valid = $true }}
                elseif ($s.Name -match "CPU|Core|Package|Tdie") {{ $valid = $true }}
                if ($valid -and $s.Value -gt $FinalTemp) {{ $FinalTemp = $s.Value }}
            }}
        }}
    }}
    $c.Close()
}} catch {{}}

# Fallback WMI
if ($FinalTemp -eq 0) {{
    try {{
        $wmi = Get-WmiObject -Namespace root/wmi -Class MSAcpi_ThermalZoneTemperature -EA SilentlyContinue
        if ($wmi) {{
            foreach ($z in $wmi) {{
                $t = ($z.CurrentTemperature - 2732) / 10
                if ($t -gt 20 -and $t -lt 120 -and $t -gt $FinalTemp) {{ $FinalTemp = $t }}
            }}
        }}
    }} catch {{}}
}}

Write-Host ([math]::Round($FinalTemp, 1))
"""


class MetricsModule:
    def __init__(self, api, ai):
        self.api = api
        self.ai  = ai
        self._lhm_ok = False
        self._garantir_lhm()

    # ------------------------------------------------------------------
    # Chamada principal a cada 300s
    # ------------------------------------------------------------------
    def run(self):
        m = self._coletar()
        insights = self.ai.add_sample(m)
        if insights:
            m["local_insights"] = [
                {
                    "tipo":          i.tipo,
                    "metrica":       i.metrica,
                    "msg":           i.mensagem,
                    "sev":           i.severidade,
                    "proj_dias":     i.projecao_dias
                }
                for i in insights
            ]
        self.api.post("agent-metrics", m)

    # ------------------------------------------------------------------
    # Coleta de métricas
    # ------------------------------------------------------------------
    def _coletar(self) -> dict:
        # CPU — interval=1 garante leitura real (não retorna 0.0)
        cpu = psutil.cpu_percent(interval=1)

        # Temperatura
        cpu_temp = self._temperatura()

        # RAM
        ram = psutil.virtual_memory()

        # Discos
        discos = []
        for p in psutil.disk_partitions(all=False):
            try:
                u = psutil.disk_usage(p.mountpoint)
                discos.append({
                    "device":     p.device,
                    "mountpoint": p.mountpoint,
                    "fstype":     p.fstype,
                    "total_gb":   round(u.total / 1e9, 1),
                    "usado_gb":   round(u.used  / 1e9, 1),
                    "livre_gb":   round(u.free  / 1e9, 1),
                    "uso_pct":    round(u.percent, 1),
                })
            except PermissionError:
                pass

        # Rede
        net = psutil.net_io_counters()

        # Top 5 processos
        procs = sorted(
            psutil.process_iter(["name", "cpu_percent", "memory_percent"]),
            key=lambda x: x.info.get("cpu_percent") or 0,
            reverse=True
        )[:5]

        return {
            "cpu_uso":      round(cpu, 1),
            "cpu_temp":     cpu_temp,
            "ram_total_mb": int(ram.total   / 1_000_000),
            "ram_uso_mb":   int(ram.used    / 1_000_000),
            "ram_uso_pct":  round(ram.percent, 1),
            "disco_json":   discos,
            "rede_json": {
                "bytes_sent": net.bytes_sent,
                "bytes_recv": net.bytes_recv,
            },
            "processos_json": [
                {
                    "nome":    p.info["name"],
                    "cpu_pct": round(p.info.get("cpu_percent")    or 0, 1),
                    "ram_pct": round(p.info.get("memory_percent") or 0, 1),
                }
                for p in procs
            ],
        }

    # ------------------------------------------------------------------
    # Temperatura — LHM via PowerShell, fallback psutil
    # ------------------------------------------------------------------
    def _temperatura(self) -> float | None:
        # Tenta LHM primeiro (Windows)
        if platform.system() == "Windows" and self._lhm_ok:
            try:
                script = _PS_TEMP.format(
                    dll=str(LHM_DLL),
                    hid=str(LHM_HID)
                )
                r = subprocess.run(
                    ["powershell", "-NonInteractive", "-Command", script],
                    capture_output=True, text=True, timeout=20
                )
                val = r.stdout.strip().split("\n")[-1].strip()
                t = float(val)
                if t > 0:
                    return round(t, 1)
            except Exception as e:
                log.warning(f"LHM temperatura falhou: {e}")

        # Fallback psutil (Linux / macOS / alguns Windows)
        try:
            temps = psutil.sensors_temperatures()
            for key in ("coretemp", "cpu_thermal", "k10temp", "acpitz"):
                if key in temps:
                    return round(max(x.current for x in temps[key]), 1)
        except Exception:
            pass

        return None

    # ------------------------------------------------------------------
    # Instala LibreHardwareMonitor se necessário
    # ------------------------------------------------------------------
    def _garantir_lhm(self):
        if platform.system() != "Windows":
            return

        if LHM_DLL.exists() and LHM_HID.exists():
            self._lhm_ok = True
            log.info("LHM já instalado")
            return

        try:
            import urllib.request, zipfile
            LHM_DIR.mkdir(parents=True, exist_ok=True)
            zip_path = LHM_DIR / "LHM.zip"

            log.info("Baixando LibreHardwareMonitor...")
            urllib.request.urlretrieve(LHM_URL, zip_path)

            with zipfile.ZipFile(zip_path, "r") as z:
                for member in z.namelist():
                    fname = Path(member).name
                    if fname in ("LibreHardwareMonitorLib.dll", "HidSharp.dll"):
                        with z.open(member) as src, open(LHM_DIR / fname, "wb") as dst:
                            dst.write(src.read())

            zip_path.unlink(missing_ok=True)

            if LHM_DLL.exists():
                self._lhm_ok = True
                log.info("LHM instalado com sucesso")
            else:
                log.warning("LHM: DLL não encontrada após extração")

        except Exception as e:
            log.error(f"Falha ao instalar LHM: {e}")
