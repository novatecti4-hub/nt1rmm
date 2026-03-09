import platform, subprocess, logging, time, threading, hashlib
from dataclasses import dataclass
from pathlib import Path

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

    def run(self):
        try:
            resp = self.api.get("agent-shield-check")
            if not resp:
                return

            pendentes = resp.get("pendentes", [])
            log.info(f"Shield: {len(pendentes)} campanha(s) pendente(s)")

            for item in pendentes:
                c = Campanha(
                    id=             item.get("id", ""),
                    titulo=         item.get("titulo", "Aviso de Segurança"),
                    nivel_urgencia= item.get("nivel_urgencia", "normal"),
                )
                self._notificar(c)
                self.api.post("agent-shield-entregue", {"campanha_id": c.id})

        except Exception as e:
            log.error(f"Shield erro: {e}", exc_info=True)

    def _notificar(self, c: Campanha):
        url    = f"{self.app_url}/shield/{c.id}"
        icone  = "⚠️" if c.nivel_urgencia == "critico" else "🔒"
        titulo = f"{icone} Aviso de Segurança — NVCloud"
        corpo  = c.titulo

        if platform.system() == "Windows":
            self._notificar_windows(titulo, corpo, url)
        else:
            self._notificar_linux(titulo, corpo)

        log.info(f"Notificação enviada: {c.titulo}")

    def _notificar_windows(self, titulo: str, corpo: str, url: str):
        script = f"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

$template = @"
<toast launch="{url}">
  <visual>
    <binding template="ToastGeneric">
      <text>{titulo}</text>
      <text>{corpo}</text>
    </binding>
  </visual>
  <actions>
    <action content="Ver Campanha" arguments="{url}" activationType="protocol"/>
  </actions>
</toast>
"@

$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($template)
$toast = New-Object Windows.UI.Notifications.ToastNotification $xml
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("NVCloud Agent").Show($toast)
"""
        try:
            ps1 = Path(r"C:\ProgramData\NVCloud\notificacao.ps1")
            ps1.write_text(script, encoding="utf-8")

            CREATE_NO_WINDOW = 0x08000000
            task_name = f"NVCloudToast_{hashlib.md5(titulo.encode()).hexdigest()[:8]}"

            # Cria task que roda na sessão do usuário logado
            subprocess.Popen(
                [
                    "schtasks", "/Create", "/F",
                    "/TN", task_name,
                    "/TR", r'powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\ProgramData\NVCloud\notificacao.ps1"',
                    "/SC", "ONCE",
                    "/ST", time.strftime("%H:%M"),
                    "/RU", "INTERACTIVE",   # ← sessão do usuário logado
                    "/RL", "LIMITED",
                    "/DELAY", "0000:00"
                ],
                creationflags=CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            # Dispara imediatamente e limpa após 30s
            def _run_and_cleanup():
                time.sleep(1)
                subprocess.Popen(
                    ["schtasks", "/Run", "/TN", task_name],
                    creationflags=CREATE_NO_WINDOW,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                time.sleep(30)
                subprocess.Popen(
                    ["schtasks", "/Delete", "/TN", task_name, "/F"],
                    creationflags=CREATE_NO_WINDOW,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

            threading.Thread(target=_run_and_cleanup, daemon=True).start()
            log.info(f"Toast agendado na sessão do usuário: {titulo}")

        except Exception as e:
            log.error(f"Toast falhou: {e}")

    def _notificar_linux(self, titulo: str, corpo: str):
        try:
            subprocess.run(
                ["notify-send", "--urgency=critical",
                 "--expire-time=25000", "--icon=security-high",
                 titulo, corpo],
                capture_output=True, timeout=10
            )
        except Exception as e:
            log.error(f"Notificação Linux falhou: {e}")
