import platform, subprocess, logging, threading, hashlib
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
            import win32ts, win32security, win32process, win32con, win32api

            ps1 = Path(r"C:\ProgramData\NVCloud\notificacao.ps1")
            ps1.write_text(script, encoding="utf-8")

            # Pega a sessão ativa do console (usuário logado)
            session_id = win32ts.WTSGetActiveConsoleSessionId()
            if session_id == 0xFFFFFFFF:
                log.warning("Nenhum usuário logado no console — toast não enviado")
                return

            # Token do usuário logado nessa sessão
            user_token = win32ts.WTSQueryUserToken(session_id)

            # Duplica o token para uso primário
            dup_token = win32security.DuplicateTokenEx(
                user_token,
                win32con.TOKEN_ALL_ACCESS,
                None,
                win32security.SecurityIdentification,
                win32security.TokenPrimary
            )

            cmd = f'powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{str(ps1)}"'

            startup = win32process.STARTUPINFO()
            startup.dwFlags    = win32con.STARTF_USESHOWWINDOW
            startup.wShowWindow = win32con.SW_HIDE

            # Cria o processo NA sessão do usuário — não como SYSTEM
            win32process.CreateProcessAsUser(
                dup_token, None, cmd,
                None, None, False,
                win32con.CREATE_NO_WINDOW,
                None, None, startup
            )

            win32api.CloseHandle(user_token)
            win32api.CloseHandle(dup_token)

            log.info(f"Toast enviado na sessão do usuário (session {session_id}): {titulo}")

        except ImportError:
            log.error("pywin32 não instalado — toast não enviado")
        except Exception as e:
            log.error(f"Toast falhou: {e}", exc_info=True)

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
