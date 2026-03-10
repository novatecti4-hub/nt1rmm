#!/usr/bin/env python3
"""
NVCloud Tray — roda na sessão do usuário (Session 1)

Responsabilidades:
  - Ícone na bandeja do sistema
  - Toasts do Shield
  - Abrir chamado diretamente pelo ícone
  - Ver chamados existentes
"""
import json, threading, time, webbrowser, platform, subprocess
import sys, os, logging
from pathlib import Path

# ── Dependências ─────────────────────────────────────────────────
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
        log.warning("notify-send nao encontrado")


# ── Janela de Chamado ─────────────────────────────────────────────
def abrir_janela_chamado(api: Api, app_url: str, agent_id: str):
    """
    Abre janela Tkinter para abertura de chamado.
    Se Tkinter nao estiver disponivel, abre o navegador.
    """
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.title("NVCloud — Abrir Chamado")
        root.geometry("480x390")
        root.resizable(False, False)
        root.configure(bg="#f0f4f8")

        # Centraliza
        root.update_idletasks()
        x = (root.winfo_screenwidth()  - 480) // 2
        y = (root.winfo_screenheight() - 390) // 2
        root.geometry(f"480x390+{x}+{y}")
        root.lift()
        root.attributes("-topmost", True)

        # Header
        hdr = tk.Frame(root, bg="#1E3A5F", height=52)
        hdr.pack(fill="x")
        tk.Label(
            hdr, text="Abrir Chamado de Suporte",
            font=("Segoe UI", 13, "bold"),
            bg="#1E3A5F", fg="white", padx=18
        ).pack(side="left", pady=12)

        # Body
        body = tk.Frame(root, bg="#f0f4f8", padx=20, pady=14)
        body.pack(fill="both", expand=True)

        tk.Label(body, text="Titulo *", font=("Segoe UI", 10, "bold"),
                 bg="#f0f4f8", anchor="w").pack(fill="x")
        titulo_var = tk.StringVar()
        tk.Entry(body, textvariable=titulo_var, font=("Segoe UI", 10),
                 relief="solid", bd=1).pack(fill="x", ipady=4, pady=(2, 10))

        tk.Label(body, text="Urgencia *", font=("Segoe UI", 10, "bold"),
                 bg="#f0f4f8", anchor="w").pack(fill="x")
        urg_var = tk.StringVar(value="normal")
        frm_u = tk.Frame(body, bg="#f0f4f8")
        frm_u.pack(fill="x", pady=(2, 10))
        for lbl, val in [("Normal", "normal"), ("Importante", "importante"), ("Critico", "critico")]:
            tk.Radiobutton(
                frm_u, text=lbl, variable=urg_var, value=val,
                font=("Segoe UI", 10), bg="#f0f4f8", activebackground="#f0f4f8"
            ).pack(side="left", padx=(0, 16))

        tk.Label(body, text="Descricao *", font=("Segoe UI", 10, "bold"),
                 bg="#f0f4f8", anchor="w").pack(fill="x")
        desc_txt = tk.Text(body, font=("Segoe UI", 10), height=5,
                            relief="solid", bd=1, wrap="word")
        desc_txt.pack(fill="x", pady=(2, 8))

        status_var = tk.StringVar()
        tk.Label(body, textvariable=status_var, font=("Segoe UI", 9),
                 bg="#f0f4f8", fg="#6b7280").pack(fill="x")

        # Botoes
        def _enviar():
            titulo    = titulo_var.get().strip()
            descricao = desc_txt.get("1.0", "end").strip()
            urgencia  = urg_var.get()
            if not titulo:
                messagebox.showwarning("Campo obrigatorio", "Informe o titulo.")
                return
            if not descricao:
                messagebox.showwarning("Campo obrigatorio", "Informe a descricao.")
                return

            btn.config(state="disabled", text="Enviando...")
            status_var.set("Enviando chamado...")
            root.update()

            def _bg():
                resp = api.post("agent-novo-chamado", {
                    "agent_id":  agent_id,
                    "titulo":    titulo,
                    "descricao": descricao,
                    "urgencia":  urgencia,
                })
                cid = resp.get("id") or resp.get("chamado_id", "")
                if cid:
                    root.after(0, lambda: _ok(cid))
                else:
                    webbrowser.open(f"{app_url.rstrip('/')}/chamados/novo")
                    root.after(0, root.destroy)

            def _ok(cid):
                messagebox.showinfo(
                    "Chamado criado",
                    f"Chamado #{cid} registrado!\n\nNossa equipe entrara em contato em breve."
                )
                root.destroy()

            threading.Thread(target=_bg, daemon=True).start()

        frm_btn = tk.Frame(root, bg="#e2e8f0", padx=20, pady=10)
        frm_btn.pack(fill="x", side="bottom")

        tk.Button(frm_btn, text="Cancelar", font=("Segoe UI", 10),
                  bg="#e2e8f0", relief="flat", command=root.destroy
                  ).pack(side="right", padx=(8, 0))

        btn = tk.Button(frm_btn, text="Enviar Chamado",
                        font=("Segoe UI", 10, "bold"),
                        bg="#1E3A5F", fg="white", relief="flat",
                        padx=16, pady=6, cursor="hand2", command=_enviar)
        btn.pack(side="right")

        root.mainloop()

    except Exception as e:
        log.warning(f"Janela de chamado falhou ({e}) — abrindo no navegador")
        webbrowser.open(f"{app_url.rstrip('/')}/chamados/novo?agent={agent_id}")


# ── Loop de verificacao Shield ────────────────────────────────────
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
                    icone        = "aviso" if nivel == "critico" else "info"
                    notif_titulo = f"Aviso de Seguranca NVCloud"
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

        stop_event.wait(1800)


# ── Icone do tray ─────────────────────────────────────────────────
def criar_icone(status: str = "online") -> Image.Image:
    cores = {"online": "#0EA5E9", "offline": "#9CA3AF", "alerta": "#F59E0B"}
    cor   = cores.get(status, "#0EA5E9")
    img   = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw  = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill=cor)
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
        threading.Thread(
            target=abrir_janela_chamado,
            args=(api, app_url, agent_id),
            daemon=True
        ).start()

    def ver_chamados(_):
        webbrowser.open(f"{app_url.rstrip('/')}/chamados?agent={agent_id}")

    def verificar_agora(_):
        log.info("Verificacao manual do Shield")
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
    icon.run()


if __name__ == "__main__":
    main()
