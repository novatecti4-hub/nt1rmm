import subprocess, platform, os, logging
from pathlib import Path
log = logging.getLogger("rustdesk")

RUSTDESK_EXE = Path(r"C:\Program Files\RustDesk\RustDesk.exe")
RUSTDESK_EXE_ALT = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "RustDesk" / "RustDesk.exe"

class RustDeskModule:
    def __init__(self, api, encoded_config: str = "", senha: str = ""):
        self.api = api
        self.encoded_config = encoded_config
        self.senha = senha

    def run(self) -> str | None:
        if platform.system() != "Windows":
            return None
        exe = self._encontrar_exe()
        if not exe:
            log.info("RustDesk não encontrado, instalando...")
            self._instalar()
            exe = self._encontrar_exe()
        if not exe:
            log.error("RustDesk não encontrado após instalação")
            return None
        if self.encoded_config:
            self._aplicar_config(exe)
        if self.senha:
            self._definir_senha()
        return self._obter_id(exe)

    def _encontrar_exe(self) -> Path | None:
        for p in [RUSTDESK_EXE, RUSTDESK_EXE_ALT]:
            if p.exists():
                return p
        return None

    def _instalar(self):
        try:
            import requests
            url = "https://github.com/rustdesk/rustdesk/releases/download/1.2.6/rustdesk-1.2.6-x86_64.exe"
            dest = Path(os.environ["TEMP"]) / "RustDesk.exe"
            r = requests.get(url, timeout=180)
            dest.write_bytes(r.content)
            subprocess.run([str(dest), "--silent-install"], capture_output=True, timeout=120)
            log.info("RustDesk instalado")
        except Exception as e:
            log.error(f"Erro ao instalar RustDesk: {e}")

    def _aplicar_config(self, exe: Path):
        try:
            subprocess.run([str(exe), "--config", self.encoded_config], capture_output=True, timeout=10)
            log.info("Config RustDesk aplicada")
        except Exception as e:
            log.error(f"Erro ao aplicar config RustDesk: {e}")

    def _definir_senha(self):
        try:
            for toml_path in [
                Path(os.environ.get("APPDATA", "")) / "RustDesk" / "config" / "RustDesk.toml",
                Path(os.environ.get("LOCALAPPDATA", "")) / "RustDesk" / "config" / "RustDesk.toml",
            ]:
                if toml_path.exists():
                    content = toml_path.read_text(encoding="utf-8")
                    lines = content.splitlines()
                    nova_content = []
                    senha_definida = False
                    for line in lines:
                        if line.strip().startswith("password ="):
                            nova_content.append(f'password = "{self.senha}"')
                            senha_definida = True
                        else:
                            nova_content.append(line)
                    if not senha_definida:
                        nova_content.append(f'password = "{self.senha}"')
                    toml_path.write_text("\n".join(nova_content), encoding="utf-8")
                    log.info("Senha RustDesk definida")
                    return
        except Exception as e:
            log.error(f"Erro ao definir senha RustDesk: {e}")

    def _obter_id(self, exe: Path) -> str | None:
        for toml_path in [
            Path(os.environ.get("APPDATA", "")) / "RustDesk" / "config" / "RustDesk.toml",
            Path(os.environ.get("LOCALAPPDATA", "")) / "RustDesk" / "config" / "RustDesk.toml",
        ]:
            try:
                if toml_path.exists():
                    for line in toml_path.read_text(encoding="utf-8").splitlines():
                        if line.strip().startswith("id ="):
                            return line.split("=")[1].strip().strip('"')
            except Exception:
                pass
        try:
            r = subprocess.run([str(exe), "--get-id"], capture_output=True, text=True, timeout=10)
            if r.stdout.strip():
                return r.stdout.strip()
        except Exception:
            pass
        return None
