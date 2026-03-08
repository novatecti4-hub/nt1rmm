import subprocess, time, logging, platform, base64, os
from pathlib import Path

log = logging.getLogger("rustdesk")

RUSTDESK_EXE = r"C:\Program Files\RustDesk\rustdesk.exe"

class RustDeskModule:
    def __init__(self, api, host: str, key: str, senha: str):
        self.api   = api
        self.host  = host
        self.key   = key
        self.senha = senha

    # ------------------------------------------------------------------
    # Pública — chamada pelo HeartbeatModule para obter o ID
    # ------------------------------------------------------------------
    def get_id(self) -> str:
        if not Path(RUSTDESK_EXE).exists():
            log.warning("RustDesk não instalado — instalando agora...")
            self._instalar()

        rustdesk_id = self._cmd("--get-id")
        if rustdesk_id:
            return rustdesk_id.strip()

        log.warning("ID não obtido, reaplicando config...")
        self._aplicar_config()
        time.sleep(5)
        rustdesk_id = self._cmd("--get-id")
        return rustdesk_id.strip() if rustdesk_id else "desconhecido"

    # ------------------------------------------------------------------
    # Instalação completa (espelha o script PowerShell)
    # ------------------------------------------------------------------
    def _instalar(self):
        log.info("Iniciando instalação do RustDesk...")

        versao = self._obter_ultima_versao()
        url    = f"https://github.com/rustdesk/rustdesk/releases/download/{versao}/rustdesk-{versao}-x86_64.exe"
        dest   = r"C:\Temp\rustdesk-installer.exe"

        Path(r"C:\Temp").mkdir(parents=True, exist_ok=True)

        # Download
        log.info(f"Baixando RustDesk {versao}...")
        import urllib.request
        urllib.request.urlretrieve(url, dest)

        # Criar config ANTES de instalar (igual ao PowerShell)
        self._criar_toml_config()

        # Instalar silenciosamente
        log.info("Instalando...")
        subprocess.run([dest, "--silent-install"], timeout=120)
        time.sleep(10)

        if not Path(RUSTDESK_EXE).exists():
            raise RuntimeError("Instalação do RustDesk falhou")

        # Instalar serviço
        self._cmd("--install-service")
        time.sleep(5)

        # Aplicar config via CLI
        self._aplicar_config()

        # Definir senha
        self._cmd("--password", self.senha)
        time.sleep(2)

        # Reiniciar serviço
        subprocess.run(["sc", "stop", "RustDesk"],  capture_output=True)
        time.sleep(3)
        subprocess.run(["sc", "start", "RustDesk"], capture_output=True)
        time.sleep(5)

        # Limpar installer
        try: os.remove(dest)
        except: pass

        log.info("RustDesk instalado e configurado com sucesso!")

    # ------------------------------------------------------------------
    # Cria o RustDesk2.toml ANTES de instalar (garante config imediata)
    # ------------------------------------------------------------------
    def _criar_toml_config(self):
        appdata   = os.environ.get("APPDATA", "")
        config_dir = Path(appdata) / "RustDesk" / "config"
        config_dir.mkdir(parents=True, exist_ok=True)

        config_file = config_dir / "RustDesk2.toml"
        toml = (
            f"[options]\n"
            f"custom-rendezvous-server = '{self.host}'\n"
            f"relay-server = '{self.host}'\n"
            f"api-server = 'https://{self.host}'\n"
            f"key = '{self.key}'\n"
        )
        config_file.write_text(toml, encoding="utf-8")
        log.info(f"TOML config criada: {config_file}")

    # ------------------------------------------------------------------
    # Aplica config via CLI + Base64 (igual ao PowerShell)
    # ------------------------------------------------------------------
    def _aplicar_config(self):
        log.info("Aplicando configurações via CLI...")

        self._cmd("--option", "key",                       self.key)
        time.sleep(1)
        self._cmd("--option", "api-server",                f"https://{self.host}")
        time.sleep(1)
        self._cmd("--option", "relay-server",              self.host)
        time.sleep(1)
        self._cmd("--option", "custom-rendezvous-server",  self.host)
        time.sleep(1)

        # Também via Base64 (reforço)
        config_str = (
            f"custom-rendezvous-server={self.host},"
            f"relay-server={self.host},"
            f"api-server=https://{self.host},"
            f"key={self.key}"
        )
        config_b64 = base64.b64encode(config_str.encode()).decode()
        self._cmd("--config", config_b64)
        time.sleep(2)

        log.info("Configurações aplicadas!")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _cmd(self, *args) -> str:
        try:
            result = subprocess.run(
                [RUSTDESK_EXE, *args],
                capture_output=True, text=True, timeout=30
            )
            return (result.stdout or "").strip()
        except Exception as e:
            log.error(f"Erro ao executar rustdesk {args}: {e}")
            return ""

    def _obter_ultima_versao(self) -> str:
        try:
            import urllib.request
            req = urllib.request.Request(
                "https://github.com/rustdesk/rustdesk/releases/latest",
                headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.url.split("/")[-1].lstrip("v")
        except:
            return "1.3.6"
