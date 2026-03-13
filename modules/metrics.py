import psutil, platform, logging, subprocess, json, os
from pathlib import Path

log = logging.getLogger("metrics")

# Script PowerShell usando apenas WMI — sem LHM/WinRing0 (evita falso positivo Defender)
_PS_TEMP_WMI = r"""
$FinalTemp = 0
try {
    $wmi = Get-WmiObject -Namespace root/wmi -Class MSAcpi_ThermalZoneTemperature -EA SilentlyContinue
    if ($wmi) {
        foreach ($z in $wmi) {
            $t = ($z.CurrentTemperature - 2732) / 10
            if ($t -gt 20 -and $t -lt 120 -and $t -gt $FinalTemp) { $FinalTemp = $t }
        }
    }
} catch {}
Write-Host ([math]::Round($FinalTemp, 1))
"""


class MetricsModule:
    def __init__(self, api, ai):
        self.api = api
        self.ai  = ai

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
        cpu = psutil.cpu_percent(interval=1)
        cpu_temp = self._temperatura()

        ram = psutil.virtual_memory()

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

        net = psutil.net_io_counters()

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
    # Temperatura — WMI (Windows) ou psutil (Linux/macOS)
    # ------------------------------------------------------------------
    def _temperatura(self) -> float | None:
        if platform.system() == "Windows":
            try:
                r = subprocess.run(
                    ["powershell", "-NonInteractive", "-Command", _PS_TEMP_WMI],
                    capture_output=True, text=True, timeout=10
                )
                val = r.stdout.strip().split("\n")[-1].strip()
                t = float(val)
                if t > 0:
                    return round(t, 1)
            except Exception as e:
                log.warning(f"WMI temperatura falhou: {e}")

        # Fallback psutil (Linux / macOS)
        try:
            temps = psutil.sensors_temperatures()
            for key in ("coretemp", "cpu_thermal", "k10temp", "acpitz"):
                if key in temps:
                    return round(max(x.current for x in temps[key]), 1)
        except Exception:
            pass

        return None
