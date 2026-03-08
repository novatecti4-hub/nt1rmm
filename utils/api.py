import requests, logging
log = logging.getLogger("api")

class ApiClient:
    def __init__(self, base_url: str, agent_token: str):
        self.base = base_url.rstrip("/")
        self.s = requests.Session()
        self.s.headers.update({
            "Authorization": f"Bearer {agent_token}",
            "Content-Type": "application/json",
            "User-Agent": "NVCloudAgent/1.0"
        })

    def post(self, fn: str, data=None, timeout=15) -> dict:
        try:
            r = self.s.post(f"{self.base}/functions/v1/{fn}",
                            json=data or {}, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except requests.Timeout:
            log.warning(f"Timeout: {fn}")
        except requests.ConnectionError:
            log.warning(f"Sem conexão: {fn}")
        except Exception as e:
            log.error(f"Erro {fn}: {e}")
        return {}

    def get(self, fn: str, params=None, timeout=15) -> dict:
        try:
            r = self.s.get(f"{self.base}/functions/v1/{fn}",
                           params=params or {}, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            log.error(f"Erro GET {fn}: {e}")
        return {}
