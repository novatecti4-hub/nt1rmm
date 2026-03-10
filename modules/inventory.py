import platform, psutil, subprocess, logging, socket, json
log = logging.getLogger("inventory")


class InventoryModule:
    def __init__(self, api, agent_id: str):
        self.api      = api
        self.agent_id = agent_id

    def run(self):
        try:
            payload = {
                "agent_id":     self.agent_id,
                "fabricante":   self._get_fabricante(),
                "modelo":       self._get_modelo(),
                "processador":  self._get_cpu(),
                "ram_total_mb": self._get_ram(),
                "hostname":     socket.gethostname(),
                "arquitetura":  platform.machine(),
                "software":     self._get_software(),   # ← ADICIONADO
            }
            log.info(f"Inventory payload: hardware OK, {len(payload['software'])} softwares encontrados")
            self.api.post("agent-inventory", payload)
            log.info("Inventário enviado com sucesso")
        except Exception as e:
            log.error(f"Inventory erro: {e}", exc_info=True)

    def _get_software(self) -> list:
        """Coleta todos os programas instalados no sistema."""
        try:
            if platform.system() == "Windows":
                return self._get_software_windows()
            elif platform.system() == "Linux":
                return self._get_software_linux()
        except Exception as e:
            log.error(f"Erro ao coletar software: {e}")
        return []

    def _get_software_windows(self) -> list:
        """Coleta software instalado via registro do Windows."""
        softwares = []
        seen = set()

        # Chaves do registro onde programas ficam instalados
        reg_keys = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        ]

        try:
            import winreg

            for reg_key in reg_keys:
                try:
                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_key)
                except Exception:
                    continue

                try:
                    num_subkeys = winreg.QueryInfoKey(key)[0]
                except Exception:
                    continue

                for i in range(num_subkeys):
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        subkey = winreg.OpenKey(key, subkey_name)

                        try:
                            nome = winreg.QueryValueEx(subkey, "DisplayName")[0]
                        except Exception:
                            continue  # Sem DisplayName = não é programa visível

                        if not nome or not nome.strip():
                            continue

                        nome = nome.strip()

                        # Evita duplicatas
                        if nome.lower() in seen:
                            continue
                        seen.add(nome.lower())

                        versao = None
                        fabricante = None
                        instalado_em = None

                        try:
                            versao = winreg.QueryValueEx(subkey, "DisplayVersion")[0]
                        except Exception:
                            pass

                        try:
                            fabricante = winreg.QueryValueEx(subkey, "Publisher")[0]
                        except Exception:
                            pass

                        try:
                            data_raw = winreg.QueryValueEx(subkey, "InstallDate")[0]
                            # Formato YYYYMMDD → converte para ISO
                            if data_raw and len(data_raw) == 8:
                                instalado_em = f"{data_raw[:4]}-{data_raw[4:6]}-{data_raw[6:8]}"
                        except Exception:
                            pass

                        softwares.append({
                            "nome":        nome,
                            "versao":      versao or None,
                            "fabricante":  fabricante or None,
                            "instalado_em": instalado_em or None,
                        })

                    except Exception:
                        continue
                    finally:
                        try:
                            winreg.CloseKey(subkey)
                        except Exception:
                            pass

                winreg.CloseKey(key)

        except ImportError:
            # winreg não disponível (não é Windows)
            pass
        except Exception as e:
            log.error(f"Erro ao ler registro Windows: {e}")

        log.info(f"Software Windows: {len(softwares)} programas encontrados")
        return softwares

    def _get_software_linux(self) -> list:
        """Coleta pacotes instalados no Linux via dpkg ou rpm."""
        softwares = []

        # Tenta dpkg (Debian/Ubuntu)
        try:
            out = subprocess.check_output(
                ["dpkg-query", "-W", "-f=${Package}\t${Version}\t${Maintainer}\n"],
                timeout=30, text=True, stderr=subprocess.DEVNULL
            )
            for line in out.splitlines():
                parts = line.split("\t")
                if len(parts) >= 1 and parts[0].strip():
                    softwares.append({
                        "nome":        parts[0].strip(),
                        "versao":      parts[1].strip() if len(parts) > 1 else None,
                        "fabricante":  parts[2].strip() if len(parts) > 2 else None,
                        "instalado_em": None,
                    })
            if softwares:
                return softwares
        except Exception:
            pass

        # Tenta rpm (CentOS/RHEL/Fedora)
        try:
            out = subprocess.check_output(
                ["rpm", "-qa", "--queryformat", "%{NAME}\t%{VERSION}\t%{VENDOR}\n"],
                timeout=30, text=True, stderr=subprocess.DEVNULL
            )
            for line in out.splitlines():
                parts = line.split("\t")
                if len(parts) >= 1 and parts[0].strip():
                    softwares.append({
                        "nome":        parts[0].strip(),
                        "versao":      parts[1].strip() if len(parts) > 1 else None,
                        "fabricante":  parts[2].strip() if len(parts) > 2 else None,
                        "instalado_em": None,
                    })
        except Exception:
            pass

        return softwares

    def _get_cpu(self) -> str:
        try:
            if platform.system() == "Windows":
                out = subprocess.check_output(
                    ["wmic", "cpu", "get", "Name", "/value"],
                    timeout=10, text=True
                )
                for line in out.splitlines():
                    if "Name=" in line:
                        return line.split("=", 1)[1].strip()
            return platform.processor() or "Desconhecido"
        except Exception:
            return platform.processor() or "Desconhecido"

    def _get_ram(self) -> int:
        try:
            return round(psutil.virtual_memory().total / (1024 * 1024))
        except Exception:
            return 0

    def _get_fabricante(self) -> str:
        try:
            if platform.system() == "Windows":
                out = subprocess.check_output(
                    ["wmic", "computersystem", "get", "Manufacturer", "/value"],
                    timeout=10, text=True
                )
                for line in out.splitlines():
                    if "Manufacturer=" in line:
                        return line.split("=", 1)[1].strip()
        except Exception:
            pass
        return "Desconhecido"

    def _get_modelo(self) -> str:
        try:
            if platform.system() == "Windows":
                out = subprocess.check_output(
                    ["wmic", "computersystem", "get", "Model", "/value"],
                    timeout=10, text=True
                )
                for line in out.splitlines():
                    if "Model=" in line:
                        return line.split("=", 1)[1].strip()
        except Exception:
            pass
        return "Desconhecido"
