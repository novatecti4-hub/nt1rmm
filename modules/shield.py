import platform, subprocess, logging, webbrowser
from dataclasses import dataclass

log = logging.getLogger("shield")


@dataclass
class Campanha:
    id:             str
    titulo:         str
    nivel_urgencia: str = "normal"


class ShieldModule:
    def __init__(self, api, token: str, app_url: str):
        self.api     = api
        self.token   = token
        self.app_url = app_url.rstrip("/")

    # ------------------------------------------------------------------
    # Chamado a cada 1800s (30min) pelo agent.py
    # ------------------------------------------------------------------
    def run(self):
        try:
            resp = self.api.get("agent-shield-check")
            if not resp:
                return

            pendentes = resp.get("pendentes", [])
            log.info(f"Shield: {len(pendentes)} campanha(s) pendente(s)")

            for item in pendentes:
                c = Campanha(
                    id=            item.get("id", ""),
                    titulo=        item.get("titulo", "Aviso de Segurança"),
                    nivel_urgencia=item.get("nivel_urgencia", "normal"),
                )
                self._notificar(c)
                # Marcar como entregue
                self.api.post("agent-shield-entregue", {"campanha_id": c.id})

        except Exception as e:
            log.error(f"Shield erro: {e}", exc_info=True)

    # ------------------------------------------------------------------
    # Notificação nativa Windows / Linux
    # ------------------------------------------------------------------
    def _notificar(self, c: Campanha):
        url   = f"{self.app_url}/shield/{c.id}"
        icone = "⚠️" if c.nivel_urgencia == "critico" else "🔒"
        titulo = f"{icone} Aviso de Segurança"
        corpo  = c.titulo

        if platform.system() == "Windows":
            self._notificar_windows(titulo, corpo, url)
        else:
            self._notificar_linux(titulo, corpo, url)

        log.info(f"Notificação enviada: {c.titulo}")

    def _notificar_windows(self, titulo: str, corpo: str, url: str):
        # Usa PowerShell BurntToast ou fallback nativo
        script_burntoast = f"""
try {{
    Import-Module BurntToast -ErrorAction Stop
    $btn = New-BTButton -Content 'Ver Campanha' -Arguments '{url}'
    New-BurntToastNotification -Text '{titulo}', '{corpo}' -Button $btn
}} catch {{
    # Fallback — notificação nativa via Windows Forms
    Add-Type -AssemblyName System.Windows.Forms
    $n = New-Object System.Windows.Forms.NotifyIcon
    $n.Icon = [System.Drawing.SystemIcons]::Shield
    $n.BalloonTipTitle = '{titulo}'
    $n.BalloonTipText = '{corpo}'
    $n.BalloonTipIcon = 'Warning'
    $n.Visible = $True
    $n.ShowBalloonTip(15000)
    Start-Sleep -Seconds 1
    $n.Dispose()
}}
"""
        try:
            subprocess.run(
                ["powershell", "-NonInteractive", "-ExecutionPolicy",
                 "Bypass", "-Command", script_burntoast],
                capture_output=True, timeout=15
            )
        except Exception as e:
            log.error(f"Notificação Windows falhou: {e}")

    def _notificar_linux(self, titulo: str, corpo: str, url: str):
        try:
            subprocess.run(
                ["notify-send", "--urgency=critical",
                 "--expire-time=15000", "--icon=security-high",
                 titulo, corpo],
                capture_output=True, timeout=10
            )
        except Exception as e:
            log.error(f"Notificação Linux falhou: {e}")
