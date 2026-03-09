import json, base64, os, platform
from pathlib import Path


class Config:
    def __init__(self):
        path = self._config_path()
        if not path.exists():
            raise FileNotFoundError(f"config.json não encontrado em {path}")

        data = json.loads(path.read_text(encoding="utf-8"))

        self.token          = data["token"]
        self.supabase_url   = data["supabase_url"].rstrip("/")
        self.app_url        = data.get("app_url", "https://tech-guard-flow.lovable.app")
        self.rustdesk_senha = data.get("rustdesk_senha", "")
        self.rustdesk_host  = data.get("rustdesk_host", "")
        self.rustdesk_key   = data.get("rustdesk_key",  "")

        payload = self._decode_jwt(self.token)

        # CORREÇÃO: garante que agent_id vem do JWT ou do config
        self.agent_id       = payload.get("agent_id")       or data.get("agent_id",       "")
        self.tenant_id      = payload.get("tenant_id")      or data.get("tenant_id",      "")
        self.cliente_id     = payload.get("cliente_id")     or data.get("cliente_id",     "")
        self.dispositivo_id = payload.get("dispositivo_id") or data.get("dispositivo_id", "")

        if not self.agent_id:
            import logging
            logging.getLogger("config").warning(
                "agent_id vazio — token pode estar desatualizado. Regere o token no Lovable."
            )

    @staticmethod
    def _decode_jwt(token: str) -> dict:
        try:
            partes = token.split(".")
            if len(partes) < 2:
                return {}
            p = partes[1]
            p += "=" * (4 - len(p) % 4)
            return json.loads(base64.urlsafe_b64decode(p))
        except Exception:
            return {}

    @staticmethod
    def _config_path() -> Path:
        if platform.system() == "Windows":
            return Path(r"C:\ProgramData\NVCloud\config.json")
        return Path("/etc/nvcloud/config.json")
