import psutil, platform, logging
log = logging.getLogger("metrics")

class MetricsModule:
    def __init__(self, api, ai):
        self.api = api
        self.ai = ai

    def run(self):
        m = self.coletar()
        insights = self.ai.add_sample(m)
        if insights:
            m["local_insights"] = [
                {"tipo": i.tipo, "metrica": i.metrica,
                 "msg": i.mensagem, "sev": i.severidade,
                 "proj_dias": i.projecao_dias}
                for i in insights
            ]
        self.api.post("agent-metrics", m)

    def coletar(self) -> dict:
        cpu = psutil.cpu_percent(interval=1)
        cpu_temp = None
        try:
            t = psutil.sensors_temperatures()
            for k in ["coretemp", "cpu_thermal", "k10temp"]:
                if k in t:
                    cpu_temp = max(x.current for x in t[k])
                    break
        except Exception:
            pass

        ram = psutil.virtual_memory()
        discos = []
        for p in psutil.disk_partitions(all=False):
            try:
                u = psutil.disk_usage(p.mountpoint)
                discos.append({
                    "device": p.device, "mountpoint": p.mountpoint,
                    "fstype": p.fstype,
                    "total_gb": round(u.total / 1e9, 1),
                    "usado_gb": round(u.used / 1e9, 1),
                    "livre_gb": round(u.free / 1e9, 1),
                    "uso_pct": round(u.percent, 1)
                })
            except PermissionError:
                pass

        net = psutil.net_io_counters()
        procs = sorted(
            psutil.process_iter(["name", "cpu_percent", "memory_percent"]),
            key=lambda x: x.info["cpu_percent"] or 0, reverse=True
        )[:5]

        return {
            "cpu_uso": round(cpu, 1),
            "cpu_temp": cpu_temp,
            "ram_total_mb": ram.total // 1_000_000,
            "ram_uso_mb": ram.used // 1_000_000,
            "ram_uso_pct": round(ram.percent, 1),
            "disco_json": discos,
            "rede_json": {"bytes_sent": net.bytes_sent, "bytes_recv": net.bytes_recv},
            "processos_json": [
                {"nome": p.info["name"],
                 "cpu_pct": round(p.info["cpu_percent"] or 0, 1),
                 "ram_pct": round(p.info["memory_percent"] or 0, 1)}
                for p in procs
            ]
        }
