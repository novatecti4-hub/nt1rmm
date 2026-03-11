import platform, subprocess, logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("shield")


@dataclass
class Campanha:
    id:                  str
    titulo:              str
    nivel_urgencia:      str = "normal"
    notificacao_titulo:  str = ""   # CORRIGIDO: campo novo da Edge Function
    notificacao_texto:   str = ""   # CORRIGIDO: campo novo da Edge Function


class ShieldModule:
    def __init__(self, api, token: str, app_url: str, agent_id: str = ""):
        self.api      = api
        self.token    = token
        self.app_url  = app_url.rstrip("/")
        self.agent_id = agent_id   # CORRIGIDO: necessário para URL e body

    def run(self):
        try:
            # CORRIGIDO: POST com agent_id (era GET sem body — servidor nunca resolvia o agente)
            resp = self.api.post("agent-shield-check", {
                "agent_id": self.agent_id
            })
            if not resp:
                return

            pendentes = resp.get("pendentes", [])
            # agent_id resolvido pelo servidor (mais confiável que o local)
            resolved_id = resp.get("agent_id", self.agent_id)
            log.info(f"Shield: {len(pendentes)} campanha(s) pendente(s)")

            for item in pendentes:
                c = Campanha(
                    id=                 item.get("id", ""),
                    titulo=             item.get("titulo", "Aviso de Segurança"),
                    nivel_urgencia=     item.get("nivel_urgencia", "normal"),
                    notificacao_titulo= item.get("notificacao_titulo", ""),
                    notificacao_texto=  item.get("notificacao_texto", ""),
                )
                self._notificar(c, resolved_id)
                self.api.post("agent-shield-entregue", {
                    "campanha_id": c.id,
                    "agent_id":    resolved_id,
                })

        except Exception as e:
            log.error(f"Shield erro: {e}", exc_info=True)

    def _notificar(self, c: Campanha, agent_id: str):
        # CORRIGIDO: URL inclui ?agent= para rastrear progresso do quiz
        url    = f"{self.app_url}/shield/{c.id}?agent={agent_id}"
        titulo = c.notificacao_titulo or (
            f"{'⚠️' if c.nivel_urgencia == 'critico' else '🔒'} Aviso de Segurança — NVCloud"
        )
        corpo  = c.notificacao_texto or c.titulo

        if platform.system() == "Windows":
            self._notificar_windows(titulo, corpo, url)
        else:
            self._notificar_linux(titulo, corpo)

        log.info(f"Notificação enviada: {c.titulo}")

    def _notificar_windows(self, titulo: str, corpo: str, url: str):
        # Mantém win32ts do repo original — cria processo na sessão do usuário
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

            session_id = win32ts.WTSGetActiveConsoleSessionId()
            if session_id == 0xFFFFFFFF:
                log.warning("Nenhum usuário logado no console — toast não enviado")
                return

            user_token = win32ts.WTSQueryUserToken(session_id)
            sa = win32security.SECURITY_ATTRIBUTES()
            dup_token  = win32security.DuplicateTokenEx(
                user_token, win32con.TOKEN_ALL_ACCESS, sa,
                win32security.SecurityIdentification, win32security.TokenPrimary
            )
            cmd     = f'powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{ps1}"'
            startup = win32process.STARTUPINFO()
            startup.dwFlags     = win32con.STARTF_USESHOWWINDOW
            startup.wShowWindow = win32con.SW_HIDE

            win32process.CreateProcessAsUser(
                dup_token, None, cmd, None, None, False,
                win32con.CREATE_NO_WINDOW, None, None, startup
            )
            win32api.CloseHandle(user_token)
            win32api.CloseHandle(dup_token)
            log.info(f"Toast enviado na sessão {session_id}: {titulo}")

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
            log.error(f"notify-send falhou: {e}")
