import pystray
import threading
import sys
import os
import platform
from PIL import Image, ImageDraw

def criar_icone():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill=(34, 197, 94), outline=(22, 163, 74), width=3)
    draw.text((20, 14), "N", fill="white")
    return img

class TrayApp:
    def __init__(self, agent):
        self.agent = agent
        self.icon = None

    def _status(self, icon, item):
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(
            "NVCloud Agent",
            f"Status: Rodando\n"
            f"Supabase: {self.agent.cfg.supabase_url}\n"
            f"Log: C:\\ProgramData\\NVCloud\\nvcloud-agent.log"
        )
        root.destroy()

    def _abrir_log(self, icon, item):
        os.startfile(r"C:\ProgramData\NVCloud\nvcloud-agent.log")

    def _desinstalar(self, icon, item):
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        confirm = messagebox.askyesno(
            "Remover NVCloud Agent",
            "Tem certeza que deseja remover o NVCloud Agent?\n\nO agente será parado e removido desta máquina."
        )
        root.destroy()
        if confirm:
            self._executar_desinstalacao()

    def _executar_desinstalacao(self):
        import subprocess, shutil
        subprocess.run(["sc", "stop", "NVCloudAgent"], capture_output=True)
        subprocess.run(["sc", "delete", "NVCloudAgent"], capture_output=True)
        try:
            shutil.rmtree(r"C:\ProgramData\NVCloud", ignore_errors=True)
        except Exception:
            pass
        if self.icon:
            self.icon.stop()
        self.agent.stop()

    def _sair(self, icon, item):
        if self.icon:
            self.icon.stop()
        self.agent.stop()

    def iniciar(self):
        if platform.system() != "Windows":
            return
        menu = pystray.Menu(
            pystray.MenuItem("NVCloud Agent", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("✅ Status", self._status),
            pystray.MenuItem("📄 Ver Log", self._abrir_log),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("🗑️ Desinstalar", self._desinstalar),
            pystray.MenuItem("❌ Fechar", self._sair),
        )
        self.icon = pystray.Icon(
            name="NVCloudAgent",
            icon=criar_icone(),
            title="NVCloud Agent — Rodando",
            menu=menu
        )
        t = threading.Thread(target=self.icon.run, daemon=True)
        t.start()
