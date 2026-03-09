import logging, subprocess, sys

log = logging.getLogger("commands")


class CommandsModule:
    def __init__(self, api):
        self.api             = api
        self._jobs_pendentes = []  # CORRIGIDO: jobs chegam via heartbeat, não via checkin

    def atualizar_jobs(self, jobs: list):
        """Chamado pelo HeartbeatModule com os jobs retornados pelo checkin."""
        self._jobs_pendentes = jobs or []

    def run(self):
        # CORRIGIDO: não chama mais agent-checkin com {} a cada 30s
        jobs = list(self._jobs_pendentes)
        self._jobs_pendentes = []
        for job in jobs:
            self._executar(job)

    def _executar(self, job: dict):
        job_id   = job.get("id")
        comando  = job.get("comando", "")
        linguagem = job.get("linguagem", "powershell")
        try:
            if linguagem == "powershell":
                r = subprocess.run(
                    ["powershell", "-NonInteractive", "-Command", comando],
                    capture_output=True, text=True, timeout=120
                )
            elif linguagem == "bash":
                r = subprocess.run(
                    ["bash", "-c", comando],
                    capture_output=True, text=True, timeout=120
                )
            elif linguagem == "python":
                r = subprocess.run(
                    [sys.executable, "-c", comando],
                    capture_output=True, text=True, timeout=120
                )
            else:
                r = subprocess.run(
                    comando, shell=True,
                    capture_output=True, text=True, timeout=120
                )
            resultado, codigo = r.stdout + r.stderr, r.returncode
        except subprocess.TimeoutExpired:
            resultado, codigo = "Timeout: comando excedeu 120 segundos", -1
        except Exception as e:
            resultado, codigo = str(e), -1

        self.api.post("agent-job-result", {
            "job_id":      job_id,
            "resultado":   resultado[:10000],
            "codigo_saida": codigo,
        })
