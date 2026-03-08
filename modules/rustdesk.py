import subprocess, logging, time, os, tempfile
from pathlib import Path

log = logging.getLogger("rustdesk")

RUSTDESK_EXE = r"C:\Program Files\RustDesk\rustdesk.exe"
PS1_PATH     = r"C:\ProgramData\NVCloud\install_rustdesk.ps1"

# Seu script original — salvo em arquivo, sem problema de escape
PS1_CONTEUDO = '''
$ErrorActionPreference = 'SilentlyContinue'
$HostIP      = "104.234.186.92"
$Key         = "8oNaKiU7X8mYDwr9XU4T4tRH4KYgVLLD6rJxMr4n8bM="
$rustdesk_pw = "Novatecti@4321"
$logFile     = "C:\\ProgramData\\NVCloud\\rustdesk-install.log"

function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $logFile -Value "[$timestamp] $Message" -ErrorAction SilentlyContinue
    Write-Host "[$timestamp] $Message"
}

function Remove-RustDeskCompletely {
    Write-Log "=== REMOVENDO RUSTDESK ANTERIOR ==="
    try {
        Get-Process -Name "rustdesk" -ErrorAction SilentlyContinue | Stop-Process -Force
        Start-Sleep -Seconds 2
        $service = Get-Service -Name "RustDesk" -ErrorAction SilentlyContinue
        if ($service) {
            Stop-Service -Name "RustDesk" -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
            $rd = "C:\\Program Files\\RustDesk\\rustdesk.exe"
            if (Test-Path $rd) { & $rd --uninstall-service; Start-Sleep -Seconds 3 }
            sc.exe delete RustDesk
        }
        @(
            "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\RustDesk",
            "HKLM:\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\RustDesk"
        ) | ForEach-Object {
            if (Test-Path $_) {
                $u = (Get-ItemProperty -Path $_ -Name "UninstallString" -EA SilentlyContinue).UninstallString
                if ($u) { cmd /c "$u /VERYSILENT /SUPPRESSMSGBOXES /NORESTART"; Start-Sleep -Seconds 5 }
            }
        }
        @(
            "C:\\Program Files\\RustDesk",
            "C:\\Program Files (x86)\\RustDesk",
            "$env:APPDATA\\RustDesk",
            "$env:LocalAppData\\RustDesk"
        ) | ForEach-Object { if (Test-Path $_) { Remove-Item $_ -Recurse -Force -EA SilentlyContinue } }
        @(
            "HKLM:\\SOFTWARE\\RustDesk",
            "HKLM:\\SOFTWARE\\WOW6432Node\\RustDesk",
            "HKCU:\\SOFTWARE\\RustDesk"
        ) | ForEach-Object { if (Test-Path $_) { Remove-Item $_ -Recurse -Force -EA SilentlyContinue } }
        Write-Log "[OK] Remocao completa"
        Start-Sleep -Seconds 3
    } catch { Write-Log "[AVISO] $($_.Exception.Message)" }
}

function Get-LatestRustDeskVersion {
    try {
        $req = [System.Net.WebRequest]::Create("https://github.com/rustdesk/rustdesk/releases/latest")
        $res = $req.GetResponse()
        $ver = $res.ResponseUri.OriginalString.split("/")[-1].Trim("v")
        $res.Close()
        return $ver
    } catch { return "1.3.8" }
}

# === INICIO ===
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

Remove-RustDeskCompletely

$RDLATEST    = Get-LatestRustDeskVersion
Write-Log "Versao: $RDLATEST"

New-Item -ItemType Directory -Force -Path "C:\\Temp" | Out-Null
$installerPath = "C:\\Temp\\rustdesk-installer.exe"
$downloadUrl   = "https://github.com/rustdesk/rustdesk/releases/download/$RDLATEST/rustdesk-$RDLATEST-x86_64.exe"

Write-Log "Baixando $downloadUrl"
if (Test-Path $installerPath) { Remove-Item $installerPath -Force }
$wc = New-Object System.Net.WebClient
$wc.DownloadFile($downloadUrl, $installerPath)
$wc.Dispose()

if (!(Test-Path $installerPath)) { Write-Host "RUSTDESK_ID=ERRO_DOWNLOAD"; exit 1 }
Write-Log "[OK] Download: $([math]::Round((Get-Item $installerPath).Length/1MB,2)) MB"

# Config ANTES de instalar
$configDir = "$env:APPDATA\\RustDesk\\config"
if (!(Test-Path $configDir)) { New-Item -ItemType Directory -Force -Path $configDir | Out-Null }
$tomlContent = "[options]`ncustom-rendezvous-server = '$HostIP'`nrelay-server = '$HostIP'`napi-server = 'https://$HostIP'`nkey = '$Key'"
$tomlContent | Out-File -FilePath "$configDir\\RustDesk2.toml" -Encoding UTF8 -Force
Write-Log "[OK] TOML criado"

# Instalar
$proc = Start-Process -FilePath $installerPath -ArgumentList "--silent-install" -PassThru -NoNewWindow
$t = 0
while (!$proc.HasExited -and $t -lt 120) { Start-Sleep -Seconds 5; $t += 5 }
Start-Sleep -Seconds 10

$rustdeskExe = "$env:ProgramFiles\\RustDesk\\rustdesk.exe"
if (!(Test-Path $rustdeskExe)) { Write-Host "RUSTDESK_ID=ERRO_INSTALACAO"; exit 1 }
Write-Log "[OK] RustDesk instalado"

Set-Location "$env:ProgramFiles\\RustDesk"
& .\\rustdesk.exe --install-service; Start-Sleep -Seconds 5

# Config via CLI
& .\\rustdesk.exe --option "key" $Key;                             Start-Sleep -Seconds 2
& .\\rustdesk.exe --option "api-server" "https://$HostIP";        Start-Sleep -Seconds 2
& .\\rustdesk.exe --option "relay-server" $HostIP;                Start-Sleep -Seconds 2
& .\\rustdesk.exe --option "custom-rendezvous-server" $HostIP;    Start-Sleep -Seconds 2

# Base64
$b64 = [System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes("custom-rendezvous-server=$HostIP,relay-server=$HostIP,api-server=https://$HostIP,key=$Key"))
& .\\rustdesk.exe --config $b64; Start-Sleep -Seconds 3

# Senha
& .\\rustdesk.exe --password $rustdesk_pw; Start-Sleep -Seconds 3
Write-Log "[OK] Senha definida"

# Reiniciar servico
Restart-Service -Name "RustDesk" -Force -EA SilentlyContinue
Start-Sleep -Seconds 5

# Obter ID
Start-Sleep -Seconds 3
$id = (& .\\rustdesk.exe --get-id 2>$null).Trim()
if (-not $id) {
    Start-Sleep -Seconds 10
    $id = (& .\\rustdesk.exe --get-id 2>$null).Trim()
}

Remove-Item $installerPath -Force -EA SilentlyContinue
Write-Log "[OK] ID: $id"
Write-Host "RUSTDESK_ID=$id"
'''

PS1_GET_ID = '''
$ErrorActionPreference = 'SilentlyContinue'
Set-Location "$env:ProgramFiles\\RustDesk"
Start-Sleep -Seconds 2
$id = (& .\\rustdesk.exe --get-id 2>$null).Trim()
Write-Host "RUSTDESK_ID=$id"
'''


class RustDeskModule:
    def __init__(self, api, host: str = None, key: str = None, senha: str = None):
        self.api = api
        self._garantir_scripts()

    def get_id(self) -> str:
        if not Path(RUSTDESK_EXE).exists():
            log.info("RustDesk não encontrado — instalando...")
            return self._executar_ps1(PS1_PATH, timeout=300)
        else:
            log.info("RustDesk já instalado — obtendo ID...")
            return self._executar_ps1(PS1_PATH + ".getid.ps1", timeout=30)

    # ------------------------------------------------------------------
    # Salva os scripts .ps1 em disco na inicialização do agente
    # ------------------------------------------------------------------
    def _garantir_scripts(self):
        Path(r"C:\ProgramData\NVCloud").mkdir(parents=True, exist_ok=True)
        # Script de instalação completo
        Path(PS1_PATH).write_text(PS1_CONTEUDO, encoding="utf-8")
        # Script só para pegar ID
        Path(PS1_PATH + ".getid.ps1").write_text(PS1_GET_ID, encoding="utf-8")
        log.info("Scripts RustDesk salvos em disco")

    # ------------------------------------------------------------------
    # Executa um .ps1 e extrai o ID da saída
    # ------------------------------------------------------------------
    def _executar_ps1(self, ps1_file: str, timeout: int = 60) -> str:
        try:
            r = subprocess.run(
                [
                    "powershell",
                    "-ExecutionPolicy", "Bypass",
                    "-NonInteractive",
                    "-File", ps1_file
                ],
                capture_output=True, text=True, timeout=timeout
            )
            output = (r.stdout or "") + (r.stderr or "")
            log.info(f"PS1 output tail: {output[-300:]}")
            return self._extrair_id(output)
        except subprocess.TimeoutExpired:
            log.error(f"Timeout ao executar {ps1_file}")
            return "desconhecido"
        except Exception as e:
            log.error(f"Erro ao executar {ps1_file}: {e}")
            return "desconhecido"

    def _extrair_id(self, output: str) -> str:
        for line in reversed(output.splitlines()):
            if "RUSTDESK_ID=" in line:
                rustdesk_id = line.split("RUSTDESK_ID=", 1)[-1].strip()
                if rustdesk_id and rustdesk_id not in ("", "ERRO_DOWNLOAD", "ERRO_INSTALACAO"):
                    log.info(f"RustDesk ID: {rustdesk_id}")
                    return rustdesk_id
        log.warning("ID não encontrado no output")
        return "desconhecido"
