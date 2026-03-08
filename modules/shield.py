import platform, subprocess, logging
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
        url   = f"{self.app_url}/shield/{c.id}"
        icone = "⚠️" if c.nivel_urgencia == "critico" else "🔒"
        titulo = f"{icone} Aviso de Segurança — NVCloud"
        corpo  = c.titulo

        if platform.system() == "Windows":
            self._notificar_windows(titulo, corpo, url)
        else:
            self._notificar_linux(titulo, corpo)

        log.info(f"Notificação enviada: {c.titulo}")

    # ------------------------------------------------------------------
    # Windows — winotify (sem PowerShell, clique abre o link)
    # ------------------------------------------------------------------
    def _notificar_windows(self, titulo: str, corpo: str, url: str):
        try:
            from winotify import Notification, audio

            toast = Notification(
                app_id="NVCloud Agent",
                title=titulo,
                msg=corpo,
                duration="long",   # fica 25s na tela
                launch=url         # clique no corpo abre o link
            )
            toast.add_actions(
                label="📋 Ver Quiz",
                launch=url
            )
            toast.set_audio(audio.Default, loop=False)
            toast.show()

        except ImportError:
            # Fallback se winotify não estiver disponível
            log.warning("winotify não encontrado — usando fallback PowerShell")
            self._notificar_windows_fallback(titulo, corpo, url)
        except Exception as e:
            log.error(f"Notificação Windows falhou: {e}")
            self._notificar_windows_fallback(titulo, corpo, url)

    def _notificar_windows_fallback(self, titulo: str, corpo: str, url: str):
        """Abre o link direto se a notificação falhar"""
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Linux
    # ------------------------------------------------------------------
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
