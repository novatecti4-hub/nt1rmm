import logging
log = logging.getLogger("commands")

class CommandsModule:
    def __init__(self, api):
        self.api = api

    def run(self):
        resp = self.api.post("agent-checkin", {})
        jobs = resp.get("jobs", [])
        for job in jobs:
            self._executar(job)

    def _executar(self, job: dict):
        import subprocess, sys
        job_id = job.get("id")
        comando = job.get("comando", "")
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
                r = subprocess.run(comando, shell=True,
                                   capture_output=True, text=True, timeout=120)

            resultado = r.stdout + r.stderr
            codigo = r.returncode
        except subprocess.TimeoutExpired:
            resultado = "Timeout: comando excedeu 120 segundos"
            codigo = -1
        except Exception as e:
            resultado = str(e)
            codigo = -1

        self.api.post("agent-job-result", {
            "job_id": job_id,
            "resultado": resultado[:10000],
            "codigo_saida": codigo
        })
