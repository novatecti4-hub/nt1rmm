import subprocess, time, logging, base64, os, urllib.request
from pathlib import Path

log = logging.getLogger("rustdesk")

RUSTDESK_EXE  = r"C:\Program Files\RustDesk\rustdesk.exe"
RUSTDESK_TOML = Path(os.environ.get("APPDATA", r"C:\Users\Default\AppData\Roaming")) / "RustDesk" / "config" / "RustDesk2.toml"


class RustDeskModule:
    def __init__(self, api, host: str, key: str, senha: str):
        self.api   = api
        self.host  = host
        self.key   = key
        self.senha = senha

    # ------------------------------------------------------------------
    # Pública — chamada pelo HeartbeatModule
    # ------------------------------------------------------------------
    def get_id(self) -> str:
        if not Path(RUSTDESK_EXE).exists():
            log.info("RustDesk não encontrado, instalando...")
            self._instalar()
        else:
            log.info("RustDesk já instalado, reaplicando configuração...")
            self._parar_servico()
            self._criar_toml_config()
            self._aplicar_config_cli()
            self._definir_senha()
            self._reiniciar_servico()

        time.sleep(5)
        rustdesk_id = self._cmd("--get-id")

        if not rustdesk_id:
            log.warning("ID vazio, tentando novamente em 10s...")
            time.sleep(10)
            rustdesk_id = self._cmd("--get-id")

        rustdesk_id = rustdesk_id.strip() if rustdesk_id else "desconhecido"
        log.info(f"RustDesk ID: {rustdesk_id}")
        return rustdesk_id

    # ------------------------------------------------------------------
    # Instalação completa
    # ------------------------------------------------------------------
    def _instalar(self):
        versao = self._obter_ultima_versao()
        url    = f"https://github.com/rustdesk/rustdesk/releases/download/{versao}/rustdesk-{versao}-x86_64.exe"
        dest   = r"C:\ProgramData\NVCloud\rustdesk-installer.exe"

        Path(r"C:\ProgramData\NVCloud").mkdir(parents=True, exist_ok=True)

        log.info(f"Baixando RustDesk {versao}...")
        urllib.request.urlretrieve(url, dest)

        # Criar config ANTES de instalar
        self._criar_toml_config()

        log.info("Instalando RustDesk silenciosamente...")
        subprocess.run([dest, "--silent-install"], timeout=120)
        time.sleep(10)

        if not Path(RUSTDESK_EXE).exists():
            raise RuntimeError("Falha ao instalar RustDesk")

        log.info("RustDesk instalado")

        # Instalar serviço
        self._cmd("--install-service")
        time.sleep(5)

        # Aplicar config via CLI
        self._aplicar_config_cli()

        # Definir senha
        self._definir_senha()

        # Reiniciar serviço
        self._reiniciar_servico()

        # Limpar installer
        try: os.remove(dest)
        except: pass

    # ------------------------------------------------------------------
    # Cria RustDesk2.toml CORRETO (sobrescreve completamente)
    # ------------------------------------------------------------------
    def _criar_toml_config(self):
        RUSTDESK_TOML.parent.mkdir(parents=True, exist_ok=True)

        toml = (
            f"[options]\n"
            f"custom-rendezvous-server = '{self.host}'\n"
            f"relay-server = '{self.host}'\n"
            f"api-server = 'https://{self.host}'\n"
            f"key = '{self.key}'\n"
        )

        # Escreve sem BOM e sobrescreve qualquer config anterior
        RUSTDESK_TOML.write_text(toml, encoding="utf-8")
        log.info(f"TOML config criada: {RUSTDESK_TOML}")

    # ------------------------------------------------------------------
    # Aplica config via CLI + Base64
    # ------------------------------------------------------------------
    def _aplicar_config_cli(self):
        log.info("Aplicando configurações via CLI...")

        cmds = [
            ("--option", "custom-rendezvous-server", self.host),
            ("--option", "relay-server",             self.host),
            ("--option", "api-server",               f"https://{self.host}"),
            ("--option", "key",                      self.key),
        ]
        for args in cmds:
            self._cmd(*args)
            time.sleep(1)

        # Reforço via Base64
        config_str = (
            f"custom-rendezvous-server={self.host},"
            f"relay-server={self.host},"
            f"api-server=https://{self.host},"
            f"key={self.key}"
        )
        config_b64 = base64.b64encode(config_str.encode()).decode()
        self._cmd("--config", config_b64)
        time.sleep(1)

        log.info("Config RustDesk aplicada")

    # ------------------------------------------------------------------
    # Define senha
    # ------------------------------------------------------------------
    def _definir_senha(self):
        self._cmd("--password", self.senha)
        time.sleep(1)
        log.info("Senha RustDesk definida")

    # ------------------------------------------------------------------
    # Controle do serviço
    # ------------------------------------------------------------------
    def _parar_servico(self):
        subprocess.run(["sc", "stop", "RustDesk"], capture_output=True)
        time.sleep(3)

    def _reiniciar_servico(self):
        subprocess.run(["sc", "stop",  "RustDesk"], capture_output=True)
        time.sleep(3)
        subprocess.run(["sc", "start", "RustDesk"], capture_output=True)
        time.sleep(5)
        log.info("Serviço RustDesk reiniciado")

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
            log.error(f"Erro rustdesk {args}: {e}")
            return ""

    def _obter_ultima_versao(self) -> str:
        try:
            req = urllib.request.Request(
                "https://github.com/rustdesk/rustdesk/releases/latest",
                headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.url.split("/")[-1].lstrip("v")
        except:
            log.warning("Não foi possível obter versão, usando 1.3.8")
            return "1.3.8"
