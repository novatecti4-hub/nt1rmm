import json, base64, os, platform
from pathlib import Path


class Config:
    def __init__(self):
        path = self._config_path()
        if not path.exists():
            raise FileNotFoundError(f"config.json não encontrado em {path}")

        data = json.loads(path.read_text(encoding="utf-8"))

        # Dados diretos do config.json
        self.token          = data["token"]
        self.supabase_url   = data["supabase_url"].rstrip("/")
        self.app_url        = data.get("app_url", "https://tech-guard-flow.lovable.app")
        self.rustdesk_senha = data.get("rustdesk_senha", "Novatecti@4321")

        # RustDesk — host e key extraídos do rustdesk_config (base64) ou fallback fixo
        self.rustdesk_host  = data.get("rustdesk_host", "104.234.186.92")
        self.rustdesk_key   = data.get("rustdesk_key",  "8oNaKiU7X8mYDwr9XU4T4tRH4KYgVLLD6rJxMr4n8bM=")

        # Decodifica o JWT para extrair IDs — não precisam estar no config.json
        payload = self._decode_jwt(self.token)

        self.agent_id       = payload.get("agent_id")       or data.get("agent_id",       "")
        self.tenant_id      = payload.get("tenant_id")      or data.get("tenant_id",      "")
        self.cliente_id     = payload.get("cliente_id")     or data.get("cliente_id",     "")
        self.dispositivo_id = payload.get("dispositivo_id") or data.get("dispositivo_id", "")

        # Aviso se campos críticos estiverem vazios
        if not self.agent_id:
            import logging
            logging.getLogger("config").warning(
                "agent_id vazio — token pode estar desatualizado. "
                "Regere o token no Lovable."
            )
        if not self.dispositivo_id:
            import logging
            logging.getLogger("config").warning(
                "dispositivo_id vazio — inventário e métricas não serão "
                "associados ao dispositivo. Regere o token no Lovable."
            )

    # ------------------------------------------------------------------
    # Decodifica payload do JWT sem verificar assinatura
    # ------------------------------------------------------------------
    @staticmethod
    def _decode_jwt(token: str) -> dict:
        try:
            partes = token.split(".")
            if len(partes) < 2:
                return {}
            payload_b64 = partes[1]
            # Corrigir padding base64
            payload_b64 += "=" * (4 - len(payload_b64) % 4)
            decoded = base64.urlsafe_b64decode(payload_b64)
            return json.loads(decoded)
        except Exception:
            return {}

    # ------------------------------------------------------------------
    # Caminho do config.json por plataforma
    # ------------------------------------------------------------------
    @staticmethod
    def _config_path() -> Path:
        if platform.system() == "Windows":
            return Path(r"C:\ProgramData\NVCloud\config.json")
        return Path("/etc/nvcloud/config.json")
