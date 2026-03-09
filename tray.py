#!/usr/bin/env python3
"""
NVCloud Tray — roda na sessão do usuário (Session 1)
Responsável por: ícone na bandeja + toasts do Shield
"""
import json, threading, time, webbrowser, platform, subprocess, sys, os, logging
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
        log.error(f"config.json não encontrado em {path}")
        sys.exit(1)
    return json.loads(path.read_text())

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

# ── Toast Windows (winotify) ──────────────────────────────────────
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
        # Fallback: PowerShell BalloonTip
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
        log.warning("notify-send não encontrado — instale libnotify-bin")

# ── Loop de verificação Shield ────────────────────────────────────
def shield_loop(api: Api, app_url: str, stop_event: threading.Event):
    log.info("Shield loop iniciado (intervalo: 30 min)")
    while not stop_event.is_set():
        try:
            resp = api.get("agent-shield-check")
            pendentes = resp.get("pendentes", [])
            log.info(f"Shield: {len(pendentes)} campanha(s) pendente(s)")
            for c in pendentes:
                cid    = c.get("id", "")
                titulo = c.get("titulo", "Aviso de Segurança")
                nivel  = c.get("nivel_urgencia", "normal")
                icone  = "⚠️" if nivel == "critico" else "🔒"
                titulo_notif = f"{icone} {titulo}"
                url    = f"{app_url.rstrip('/')}/shield/{cid}"

                if platform.system() == "Windows":
                    mostrar_toast_windows(titulo_notif, "Clique para ver o aviso de segurança", url)
                else:
                    mostrar_toast_linux(titulo_notif, "Clique para ver o aviso de segurança")

                api.post("agent-shield-entregue", {"campanha_id": cid})

        except Exception as e:
            log.error(f"Erro no shield_loop: {e}", exc_info=True)

        stop_event.wait(1800)  # 30 minutos

# ── Ícone do tray (gerado dinamicamente) ─────────────────────────
def criar_icone() -> Image.Image:
    img  = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Círculo azul NVCloud
    draw.ellipse([4, 4, 60, 60], fill="#0EA5E9")
    # Letra N branca simplificada
    draw.line([(18, 16), (18, 48)], fill="white", width=5)
    draw.line([(18, 16), (46, 48)], fill="white", width=5)
    draw.line([(46, 16), (46, 48)], fill="white", width=5)
    return img

# ── Menu do tray ──────────────────────────────────────────────────
def build_menu(app_url: str, stop_event: threading.Event, icon_ref: list):
    def abrir_painel(_):
        webbrowser.open(app_url)

    def verificar_agora(_):
        log.info("Verificação manual do Shield solicitada")
        stop_event.set()
        stop_event.clear()

    def sair(_):
        log.info("Encerrando tray...")
        stop_event.set()
        if icon_ref:
            icon_ref[0].stop()

    return pystray.Menu(
        pystray.MenuItem("NVCloud — Online ✅", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("🌐 Abrir painel", abrir_painel),
        pystray.MenuItem("🔍 Verificar Shield agora", verificar_agora),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("❌ Sair", sair),
    )

# ── Main ──────────────────────────────────────────────────────────
def main():
    cfg     = load_config()
    token   = cfg["token"]
    sup_url = cfg["supabase_url"]
    app_url = cfg.get("app_url", "https://app.nvcloud.com.br")

    api        = Api(sup_url, token)
    stop_event = threading.Event()
    icon_ref   = []

    # Inicia loop Shield em background
    t = threading.Thread(target=shield_loop, args=(api, app_url, stop_event), daemon=True)
    t.start()

    # Cria ícone do tray
    imagem = criar_icone()
    menu   = build_menu(app_url, stop_event, icon_ref)
    icon   = pystray.Icon("NVCloud", imagem, "NVCloud Agent", menu)
    icon_ref.append(icon)

    log.info("Tray iniciado")
    icon.run()  # bloqueia até sair()

if __name__ == "__main__":
    main()
