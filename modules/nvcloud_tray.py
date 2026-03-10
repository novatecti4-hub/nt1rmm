#!/usr/bin/env python3
"""
NVCloud Tray — roda na sessão do usuário (Session 1)

Responsabilidades:
  - Ícone na bandeja do sistema
  - Toasts do Shield (campanhas de segurança)
  - Abrir chamado no navegador via página /abrir-chamado do sistema
  - Ver chamados existentes no painel
"""
import json, threading, webbrowser, platform, subprocess
import sys, os, logging, socket
from pathlib import Path

# ── Dependências ─────────────────────────────────────────────────
# pip install pystray pillow winotify requests
import pystray
from PIL import Image, ImageDraw
import requests

# ── Log ──────────────────────────────────────────────────────────
LOG_DIR = r"C:\ProgramData\NVCloud" if platform.system() == "Windows" else "/var/log/nvcloud"
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(LOG_DIR, "tray.log"), encoding="utf-8"),
    ],
)
log = logging.getLogger("tray")


# ── Config ────────────────────────────────────────────────────────
def load_config() -> dict:
    path = Path(r"C:\ProgramData\NVCloud\config.json") if platform.system() == "Windows" \
        else Path("/etc/nvcloud/config.json")
    if not path.exists():
        log.error(f"config.json nao encontrado em {path}")
        sys.exit(1)
    return json.loads(path.read_text(encoding="utf-8"))


# ── API helper ────────────────────────────────────────────────────
class Api:
    def __init__(self, base_url: str, token: str):
        self.base = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def get(self, fn: str) -> dict:
        try:
            r = requests.get(f"{self.base}/functions/v1/{fn}",
                             headers=self.headers, timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            log.warning(f"GET {fn}: {e}")
            return {}

    def post(self, fn: str, data: dict) -> dict:
        try:
            r = requests.post(f"{self.base}/functions/v1/{fn}",
                              headers=self.headers, json=data, timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            log.warning(f"POST {fn}: {e}")
            return {}


# ── Toast Windows ─────────────────────────────────────────────────
def mostrar_toast_windows(titulo: str, mensagem: str, url: str):
    try:
        from winotify import Notification, audio
        toast = Notification(
            app_id="NVCloud Shield",
            title=titulo,
            msg=mensagem,
            duration="long",
            launch=url,
        )
        toast.set_audio(audio.Default, loop=False)
        toast.show()
        log.info(f"Toast exibido: {titulo}")
    except ImportError:
        # Fallback PowerShell BalloonTip
        script = f"""
Add-Type -AssemblyName System.Windows.Forms
$n = New-Object System.Windows.Forms.NotifyIcon
$n.Icon = [System.Drawing.SystemIcons]::Warning
$n.BalloonTipTitle = "{titulo}"
$n.BalloonTipText = "{mensagem}"
$n.Visible = $True
$n.ShowBalloonTip(15000)
Start-Sleep -Seconds 16
$n.Visible = $False
"""
        subprocess.Popen(
            ["powershell", "-WindowStyle", "Hidden", "-Command", script],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )


# ── Toast Linux ───────────────────────────────────────────────────
def mostrar_toast_linux(titulo: str, mensagem: str):
    try:
        subprocess.run(
            ["notify-send", "--urgency=critical", "--expire-time=15000",
             "--icon=security-high", titulo, mensagem],
            capture_output=True,
        )
    except FileNotFoundError:
        log.warning("notify-send nao encontrado — instale libnotify-bin")


# ── Abrir Chamado no navegador ────────────────────────────────────
def abrir_janela_chamado(api: Api, app_url: str, agent_id: str):
    """
    Abre a página /abrir-chamado do sistema no navegador,
    passando nvcloud_agent_id e hostname na URL.

    A página AbrirChamadoPublico.tsx já existente identifica o
    dispositivo automaticamente e cria o chamado + OS no sistema.

    URL gerada:
      {app_url}/abrir-chamado?nvcloud_agent_id={id}&hostname={host}&rustdesk={id}
    """
    try:
        hostname    = socket.gethostname()
        rustdesk_id = ""
        try:
            rustdesk_id = load_config().get("rustdesk_id", "")
        except Exception:
            pass

        params = f"nvcloud_agent_id={agent_id}&hostname={hostname}"
        if rustdesk_id:
            params += f"&rustdesk={rustdesk_id}"

        url = f"{app_url.rstrip('/')}/abrir-chamado?{params}"
        webbrowser.open(url)
        log.info(f"Chamado: navegador aberto em {url}")

    except Exception as e:
        log.error(f"Erro ao abrir chamado ({e}) — abrindo pagina base")
        webbrowser.open(f"{app_url.rstrip('/')}/abrir-chamado")


# ── Loop de verificação Shield ────────────────────────────────────
def shield_loop(api: Api, app_url: str, stop_event: threading.Event, agent_id: str = ""):
    log.info(f"Shield loop iniciado (30 min) — agent_id={agent_id or '(JWT)'}")
    while not stop_event.is_set():
        try:
            resp        = api.post("agent-shield-check", {"agent_id": agent_id})
            pendentes   = resp.get("pendentes", [])
            resolved_id = resp.get("agent_id", agent_id)

            log.info(f"Shield: {len(pendentes)} campanha(s) pendente(s)")
            for c in pendentes:
                cid          = c.get("id", "")
                titulo       = c.get("titulo", "Aviso de Seguranca")
                nivel        = c.get("nivel_urgencia", "normal")
                notif_titulo = c.get("notificacao_titulo", "")
                notif_texto  = c.get("notificacao_texto",  "")

                if not notif_titulo:
                    notif_titulo = "Aviso de Seguranca NVCloud"
                if not notif_texto:
                    notif_texto = titulo

                url = f"{app_url.rstrip('/')}/shield/{cid}?agent={resolved_id}"

                if platform.system() == "Windows":
                    mostrar_toast_windows(notif_titulo, notif_texto, url)
                else:
                    mostrar_toast_linux(notif_titulo, notif_texto)

                api.post("agent-shield-entregue", {
                    "campanha_id": cid,
                    "agent_id":    resolved_id,
                })

        except Exception as e:
            log.error(f"Erro no shield_loop: {e}", exc_info=True)

        stop_event.wait(1800)  # 30 minutos


# ── Ícone do tray ─────────────────────────────────────────────────
def criar_icone(status: str = "online") -> Image.Image:
    """
    Gera ícone dinamicamente.
    status: "online" (azul) | "offline" (cinza) | "alerta" (laranja)
    """
    cores = {"online": "#0EA5E9", "offline": "#9CA3AF", "alerta": "#F59E0B"}
    cor   = cores.get(status, "#0EA5E9")
    img   = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw  = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill=cor)
    # Letra N branca
    draw.line([(18, 16), (18, 48)], fill="white", width=5)
    draw.line([(18, 16), (46, 48)], fill="white", width=5)
    draw.line([(46, 16), (46, 48)], fill="white", width=5)
    return img


# ── Menu do tray ──────────────────────────────────────────────────
def build_menu(api: Api, app_url: str, agent_id: str,
               stop_event: threading.Event, icon_ref: list):

    def abrir_painel(_):
        webbrowser.open(app_url)

    def abrir_chamado(_):
        """Abre chamado em thread separada para não travar o tray."""
        threading.Thread(
            target=abrir_janela_chamado,
            args=(api, app_url, agent_id),
            daemon=True
        ).start()

    def ver_chamados(_):
        """Abre lista de chamados no painel."""
        webbrowser.open(f"{app_url.rstrip('/')}/chamados")

    def verificar_agora(_):
        """Acorda o shield_loop imediatamente."""
        log.info("Verificacao manual do Shield solicitada")
        stop_event.set()
        stop_event.clear()

    def sair(_):
        log.info("Encerrando tray...")
        stop_event.set()
        if icon_ref:
            icon_ref[0].stop()

    return pystray.Menu(
        pystray.MenuItem("NVCloud Agent  \u2705  Online", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("\U0001f310  Abrir painel",             abrir_painel),
        pystray.MenuItem("\U0001f50d  Verificar Shield agora",   verificar_agora),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("\U0001f3ab  Abrir chamado de suporte", abrir_chamado),
        pystray.MenuItem("\U0001f4cb  Ver meus chamados",        ver_chamados),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("\u274c  Sair",                         sair),
    )


# ── Main ──────────────────────────────────────────────────────────
def main():
    cfg      = load_config()
    token    = cfg["token"]
    sup_url  = cfg["supabase_url"]
    app_url  = cfg.get("app_url", "https://tech-guard-flow.lovable.app")
    agent_id = cfg.get("agent_id", "")

    api        = Api(sup_url, token)
    stop_event = threading.Event()
    icon_ref   = []

    # Inicia loop Shield em background
    threading.Thread(
        target=shield_loop,
        args=(api, app_url, stop_event, agent_id),
        daemon=True
    ).start()

    imagem = criar_icone("online")
    menu   = build_menu(api, app_url, agent_id, stop_event, icon_ref)
    icon   = pystray.Icon("NVCloud", imagem, "NVCloud Agent", menu)
    icon_ref.append(icon)

    log.info("Tray iniciado")
    icon.run()  # bloqueia até sair()


if __name__ == "__main__":
    main()
