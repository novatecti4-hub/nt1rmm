import json, platform
from pathlib import Path

class Config:
    def __init__(self):
        path = self.config_path()
        if not path.exists():
            raise FileNotFoundError(f"config.json não encontrado em {path}")
        data = json.loads(path.read_text())
        self.token = data["token"]
        self.supabase_url = data["supabase_url"]
        self.app_url = data.get("app_url", "https://app.nvcloud.com.br")
        self.rustdesk_config = data.get("rustdesk_config", "")
        self.rustdesk_senha = data.get("rustdesk_senha", "")

    @staticmethod
    def config_path() -> Path:
        if platform.system() == "Windows":
            return Path(r"C:\ProgramData\NVCloud\config.json")
        return Path("/etc/nvcloud/config.json")
