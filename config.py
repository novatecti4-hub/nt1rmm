import os
from pathlib import Path

class Config:
    def __init__(self):
        # Supabase
        self.supabase_url = os.getenv("SUPABASE_URL", "https://SEU_PROJETO.supabase.co")
        self.token        = os.getenv("NVCLOUD_TOKEN", "SEU_TOKEN")
        self.app_url      = os.getenv("APP_URL", "https://app.nvcloud.com.br")

        # RustDesk
        self.rustdesk_host  = os.getenv("RUSTDESK_HOST", "104.234.186.92")
        self.rustdesk_key   = os.getenv("RUSTDESK_KEY",  "8oNaKiU7X8mYDwr9XU4T4tRH4KYgVLLD6rJxMr4n8bM=")
        self.rustdesk_senha = os.getenv("RUSTDESK_SENHA", "Novatecti@4321")
