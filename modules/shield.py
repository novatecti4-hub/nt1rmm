import platform, subprocess, logging
from dataclasses import dataclass
log = logging.getLogger("shield")

@dataclass
class Campanha:
    id: str
    titulo: str
    nivel_urgencia: str

class ShieldModule:
    def __init__(self, api, agent_id: str, app_url: str):
        self.api = api
        self.agent_id = agent_id
        self.app_url = app_url

    def run(self):
        r = self.api.get("agent-shield-check")
        for c in r.get("pendentes", []):
            campanha = Campanha(**c)
            self._notificar(campanha)

    def _notificar(self, c: Campanha):
        url = f"{self.app_url}/shield/{c.id}?agent={self.agent_id}"
        icon = "⚠️" if c.nivel_urgencia == "critico" else "🛡️"
        titulo = f"{icon} Aviso de Segurança: {c.titulo}"

        if platform.system() == "Windows":
            script = f"""
Add-Type -AssemblyName System.Windows.Forms
$n = New-Object System.Windows.Forms.NotifyIcon
$n.Icon = [System.Drawing.SystemIcons]::Warning
$n.BalloonTipTitle = "{titulo}"
$n.BalloonTipText = "Clique para ver o aviso de segurança"
$n.Visible = $true
$n.ShowBalloonTip(15000)
Start-Sleep -Seconds 1
"""
            subprocess.run(["powershell", "-c", script], capture_output=True)
        else:
            subprocess.run([
                "notify-send",
                "--urgency=critical",
                "--expire-time=15000",
                "--icon=security-high",
                titulo,
                "Clique para ver o aviso de segurança"
            ], capture_output=True)

        self.api.post("agent-shield-entregue", {"campanha_id": c.id})
