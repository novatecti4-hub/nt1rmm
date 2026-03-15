#!/usr/bin/env python3
"""
NVCloud Tray - roda na sessao do usuario (Session 1)
"""
import json, threading, webbrowser, platform, subprocess
import sys, os, logging, socket
from pathlib import Path

import pystray
from PIL import Image, ImageDraw
import requests

LOG_DIR = r"C:\ProgramData\NVCloud" if platform.system() == "Windows" else "/var/log/nvcloud"
os.makedirs(LOG_DIR, exist_ok=True)

_handlers = [logging.StreamHandler()]
for _logfile in [os.path.join(LOG_DIR, "nvcloud-tray.log"), os.path.join(LOG_DIR, "nvcloud-fallback.log")]:
    try:
        _handlers.append(logging.FileHandler(_logfile, encoding="utf-8"))
        break
    except PermissionError:
        continue

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=_handlers,
)
log = logging.getLogger("tray")


def load_config() -> dict:
    path = Path(r"C:\ProgramData\NVCloud\config.json") if platform.system() == "Windows" \
        else Path("/etc/nvcloud/config.json")
    if not path.exists():
        log.error(f"config.json nao encontrado em {path}")
        sys.exit(1)
    return json.loads(path.read_text(encoding="utf-8"))


class Api:
    def __init__(self, base_url: str, token: str):
        self.base = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def get(self, fn: str) -> dict:
        try:
            r = requests.get(f"{self.base}/functions/v1/{fn}", headers=self.headers, timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            log.warning(f"GET {fn}: {e}")
            return {}

    def post(self, fn: str, data: dict) -> dict:
        try:
            r = requests.post(f"{self.base}/functions/v1/{fn}", headers=self.headers, json=data, timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            log.warning(f"POST {fn}: {e}")
            return {}


def mostrar_toast_windows(titulo: str, mensagem: str, url: str):
    try:
        from winotify import Notification, audio
        toast = Notification(app_id="NVCloud Shield", title=titulo, msg=mensagem, duration="long", launch=url)
        toast.set_audio(audio.Default, loop=False)
        toast.show()
        log.info(f"Toast exibido: {titulo}")
    except ImportError:
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
        subprocess.Popen(["powershell", "-WindowStyle", "Hidden", "-Command", script],
                         creationflags=subprocess.CREATE_NO_WINDOW)


def mostrar_toast_linux(titulo: str, mensagem: str):
    try:
        subprocess.run(["notify-send", "--urgency=critical", "--expire-time=15000",
                        "--icon=security-high", titulo, mensagem], capture_output=True)
    except FileNotFoundError:
        log.warning("notify-send nao encontrado")


def abrir_janela_chamado(api: Api, app_url: str, agent_id: str):
    try:
        hostname = socket.gethostname()
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
        log.error(f"Erro ao abrir chamado ({e})")
        webbrowser.open(f"{app_url.rstrip('/')}/abrir-chamado")


def shield_loop(api: Api, app_url: str, stop_event: threading.Event, agent_id: str = ""):
    log.info(f"Shield loop iniciado (30 min) - agent_id={agent_id or '(JWT)'}")
    while not stop_event.is_set():
        try:
            resp = api.post("agent-shield-check", {"agent_id": agent_id})
            pendentes = resp.get("pendentes", [])
            resolved_id = resp.get("agent_id", agent_id)
            log.info(f"Shield: {len(pendentes)} campanha(s) pendente(s)")
            for c in pendentes:
                cid = c.get("id", "")
                notif_titulo = c.get("notificacao_titulo", "") or "Aviso de Seguranca NVCloud"
                notif_texto = c.get("notificacao_texto", "") or c.get("titulo", "Aviso")
                url = f"{app_url.rstrip('/')}/shield/{cid}?agent={resolved_id}"
                if platform.system() == "Windows":
                    mostrar_toast_windows(notif_titulo, notif_texto, url)
                else:
                    mostrar_toast_linux(notif_titulo, notif_texto)
                api.post("agent-shield-entregue", {"campanha_id": cid, "agent_id": resolved_id})
        except Exception as e:
            log.error(f"Erro no shield_loop: {e}", exc_info=True)
        stop_event.wait(1800)


def criar_icone(status: str = "online") -> Image.Image:
    import math
    SIZE = 64
    NAVY = "#1a2060"
    BORDA = {"online": "#2DBD8F", "offline": "#9CA3AF", "alerta": "#EF4444"}
    PULSO = {"online": "#2DBD8F", "offline": "#E5E7EB", "alerta": "#EF4444"}
    FUNDO = {"online": NAVY, "offline": "#374151", "alerta": NAVY}
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pts = []
    for i in range(6):
        angle = math.radians(90 + i * 60)
        pts.append((SIZE/2 + 29*math.cos(angle), SIZE/2 + 29*math.sin(angle)))
    draw.polygon(pts, fill=FUNDO.get(status, NAVY))
    draw.polygon(pts, outline=NAVY, width=3)
    draw.polygon(pts, outline=BORDA.get(status, "#2DBD8F"), width=2)
    pulse = [(8,32),(16,32),(20,20),(25,44),(29,26),(33,38),(37,32),(56,32)]
    draw.line(pulse, fill=PULSO.get(status, "#2DBD8F"), width=3)
    return img


def build_menu(api: Api, app_url: str, agent_id: str, stop_event: threading.Event, icon_ref: list):
    def abrir_painel(_): webbrowser.open(app_url)
    def abrir_chamado(_):
        threading.Thread(target=abrir_janela_chamado, args=(api, app_url, agent_id), daemon=True).start()
    def ver_chamados(_): webbrowser.open(f"{app_url.rstrip('/')}/chamados")
    def verificar_agora(_):
        log.info("Verificacao manual do Shield solicitada")
        stop_event.set()
        stop_event.clear()
    def sair(_):
        log.info("Encerrando tray...")
        stop_event.set()
        if icon_ref: icon_ref[0].stop()

    return pystray.Menu(
        pystray.MenuItem("NVCloud Agent  \u2705  Online", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("\U0001f310  Abrir painel", abrir_painel),
        pystray.MenuItem("\U0001f50d  Verificar campanha agora", verificar_agora),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("\U0001f3ab  Abrir chamado de suporte", abrir_chamado),
        pystray.MenuItem("\U0001f4cb  Ver meus chamados", ver_chamados),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("\u274c  Sair", sair),
    )


def main():
    cfg = load_config()
    token = cfg["token"]
    sup_url = cfg["supabase_url"]
    app_url = cfg.get("app_url", "https://tech-guard-flow.lovable.app")
    agent_id = cfg.get("agent_id", "")

    api = Api(sup_url, token)
    stop_event = threading.Event()
    icon_ref = []

    threading.Thread(target=shield_loop, args=(api, app_url, stop_event, agent_id), daemon=True).start()

    imagem = criar_icone("online")
    menu = build_menu(api, app_url, agent_id, stop_event, icon_ref)
    icon = pystray.Icon("NVCloud", imagem, "NVCloud Agent", menu)
    icon_ref.append(icon)

    log.info("Tray iniciado")
    icon.run()


if __name__ == "__main__":
    main()
