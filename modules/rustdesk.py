import subprocess, logging, time, os
from pathlib import Path

log = logging.getLogger("rustdesk")

RUSTDESK_EXE = r"C:\Program Files\RustDesk\rustdesk.exe"

# ============================================================
# Seu script original 100% funcional — embutido aqui
# ============================================================
_PS_INSTALAR = r"""
$ErrorActionPreference = 'SilentlyContinue'
$HostIP      = "104.234.186.92"
$Key         = "8oNaKiU7X8mYDwr9XU4T4tRH4KYgVLLD6rJxMr4n8bM="
$rustdesk_pw = "Novatecti@4321"
$logFile     = "C:\ProgramData\NVCloud\rustdesk-install.log"

function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "[$timestamp] $Message"
    Write-Host $logMessage
    Add-Content -Path $logFile -Value $logMessage -ErrorAction SilentlyContinue
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
            $rustdeskExe = "C:\Program Files\RustDesk\rustdesk.exe"
            if (Test-Path $rustdeskExe) {
                & $rustdeskExe --uninstall-service
                Start-Sleep -Seconds 3
            }
            sc.exe delete RustDesk
        }
        $uninstallPaths = @(
            "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\RustDesk",
            "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\RustDesk"
        )
        foreach ($path in $uninstallPaths) {
            if (Test-Path $path) {
                $uninstallString = (Get-ItemProperty -Path $path -Name "UninstallString" -ErrorAction SilentlyContinue).UninstallString
                if ($uninstallString) {
                    cmd /c "$uninstallString /VERYSILENT /SUPPRESSMSGBOXES /NORESTART"
                    Start-Sleep -Seconds 5
                }
            }
        }
        $installDirs = @(
            "C:\Program Files\RustDesk",
            "C:\Program Files (x86)\RustDesk",
            "$env:APPDATA\RustDesk",
            "$env:LocalAppData\RustDesk"
        )
        foreach ($dir in $installDirs) {
            if (Test-Path $dir) { Remove-Item -Path $dir -Recurse -Force -ErrorAction SilentlyContinue }
        }
        $regPaths = @(
            "HKLM:\SOFTWARE\RustDesk",
            "HKLM:\SOFTWARE\WOW6432Node\RustDesk",
            "HKCU:\SOFTWARE\RustDesk"
        )
        foreach ($regPath in $regPaths) {
            if (Test-Path $regPath) { Remove-Item -Path $regPath -Recurse -Force -ErrorAction SilentlyContinue }
        }
        Write-Log "[OK] Remocao completa"
        Start-Sleep -Seconds 3
    } catch {
        Write-Log "[AVISO] Erro: $($_.Exception.Message)"
    }
}

function Get-LatestRustDeskVersion {
    try {
        $url = 'https://github.com/rustdesk/rustdesk/releases/latest'
        $request = [System.Net.WebRequest]::Create($url)
        $response = $request.GetResponse()
        $realTagUrl = $response.ResponseUri.OriginalString
        $version = $realTagUrl.split('/')[-1].Trim('v')
        $response.Close()
        return $version
    } catch {
        return "1.3.8"
    }
}

# === INICIO ===
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

Remove-RustDeskCompletely

$RDLATEST = Get-LatestRustDeskVersion
Write-Log "Versao: $RDLATEST"

New-Item -ItemType Directory -Force -Path "C:\Temp" | Out-Null
$installerPath = "C:\Temp\rustdesk-installer.exe"
$downloadUrl   = "https://github.com/rustdesk/rustdesk/releases/download/$RDLATEST/rustdesk-$RDLATEST-x86_64.exe"

Write-Log "Baixando $downloadUrl..."
if (Test-Path $installerPath) { Remove-Item $installerPath -Force }
$webClient = New-Object System.Net.WebClient
$webClient.DownloadFile($downloadUrl, $installerPath)
$webClient.Dispose()

if (!(Test-Path $installerPath)) { throw "Instalador nao encontrado" }
Write-Log "[OK] Download: $([math]::Round((Get-Item $installerPath).Length/1MB,2)) MB"

# Config ANTES de instalar
$configDir  = "$env:APPDATA\RustDesk\config"
if (!(Test-Path $configDir)) { New-Item -ItemType Directory -Force -Path $configDir | Out-Null }
$configFile = "$configDir\RustDesk2.toml"
$tomlContent = @"
[options]
custom-rendezvous-server = '$HostIP'
relay-server = '$HostIP'
api-server = 'https://$HostIP'
key = '$Key'
"@
$tomlContent | Out-File -FilePath $configFile -Encoding UTF8 -Force
Write-Log "[OK] TOML criado"

# Instalar
$process = Start-Process -FilePath $installerPath -ArgumentList "--silent-install" -PassThru -NoNewWindow
$timeout = 120; $elapsed = 0
while (!$process.HasExited -and $elapsed -lt $timeout) { Start-Sleep -Seconds 5; $elapsed += 5 }
Start-Sleep -Seconds 10

$rustdeskExe = "$env:ProgramFiles\RustDesk\rustdesk.exe"
if (!(Test-Path $rustdeskExe)) { throw "RustDesk nao instalado" }
Write-Log "[OK] RustDesk instalado"

Set-Location "$env:ProgramFiles\RustDesk"
& .\rustdesk.exe --install-service
Start-Sleep -Seconds 5

# Aplicar config via CLI
& .\rustdesk.exe --option 'key' $Key;                              Start-Sleep -Seconds 2
& .\rustdesk.exe --option 'api-server' "https://$HostIP";         Start-Sleep -Seconds 2
& .\rustdesk.exe --option 'relay-server' $HostIP;                 Start-Sleep -Seconds 2
& .\rustdesk.exe --option 'custom-rendezvous-server' $HostIP;     Start-Sleep -Seconds 2

# Base64
$configString = "custom-rendezvous-server=$HostIP,relay-server=$HostIP,api-server=https://$HostIP,key=$Key"
$configBase64 = [System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($configString))
& .\rustdesk.exe --config $configBase64
Start-Sleep -Seconds 3

# Senha
& .\rustdesk.exe --password $rustdesk_pw
Start-Sleep -Seconds 3
Write-Log "[OK] Senha definida"

# Reiniciar servico
Restart-Service -Name "RustDesk" -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 5

# Obter ID
Start-Sleep -Seconds 3
$rustdesk_id = (& .\rustdesk.exe --get-id).Trim()
if ($rustdesk_id) { Write-Log "[OK] ID: $rustdesk_id" } else { $rustdesk_id = "" }

# Limpar
Remove-Item $installerPath -Force -ErrorAction SilentlyContinue

# Retorna APENAS o ID na ultima linha (Python lê isso)
Write-Host "RUSTDESK_ID=$rustdesk_id"
"""

# Script apenas para pegar o ID (quando já instalado)
_PS_GET_ID = r"""
$ErrorActionPreference = 'SilentlyContinue'
Set-Location "$env:ProgramFiles\RustDesk"
Start-Sleep -Seconds 2
$id = (& .\rustdesk.exe --get-id 2>$null).Trim()
Write-Host "RUSTDESK_ID=$id"
"""


class RustDeskModule:
    def __init__(self, api, host: str = None, key: str = None, senha: str = None):
        self.api = api

    # ------------------------------------------------------------------
    # Pública — chamada pelo HeartbeatModule
    # ------------------------------------------------------------------
    def get_id(self) -> str:
        if not Path(RUSTDESK_EXE).exists():
            log.info("RustDesk não encontrado — instalando com script completo...")
            return self._instalar_e_obter_id()
        else:
            log.info("RustDesk já instalado — obtendo ID...")
            return self._obter_id()

    # ------------------------------------------------------------------
    # Executa o script completo de instalação e retorna o ID
    # ------------------------------------------------------------------
    def _instalar_e_obter_id(self) -> str:
        try:
            r = self._ps(_PS_INSTALAR, timeout=300)
            return self._extrair_id(r)
        except Exception as e:
            log.error(f"Erro na instalação do RustDesk: {e}")
            return "desconhecido"

    # ------------------------------------------------------------------
    # Só pega o ID (já instalado)
    # ------------------------------------------------------------------
    def _obter_id(self) -> str:
        try:
            r = self._ps(_PS_GET_ID, timeout=30)
            rustdesk_id = self._extrair_id(r)
            if rustdesk_id and rustdesk_id != "desconhecido":
                return rustdesk_id
            # Retry após 10s
            log.warning("ID vazio, aguardando serviço...")
            time.sleep(10)
            r = self._ps(_PS_GET_ID, timeout=30)
            return self._extrair_id(r)
        except Exception as e:
            log.error(f"Erro ao obter ID RustDesk: {e}")
            return "desconhecido"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _extrair_id(self, output: str) -> str:
        for line in output.splitlines():
            if "RUSTDESK_ID=" in line:
                rustdesk_id = line.split("RUSTDESK_ID=", 1)[-1].strip()
                if rustdesk_id:
                    log.info(f"RustDesk ID: {rustdesk_id}")
                    return rustdesk_id
        log.warning(f"ID não encontrado no output: {output[:200]}")
        return "desconhecido"

    def _ps(self, script: str, timeout: int = 60) -> str:
        try:
            r = subprocess.run(
                ["powershell", "-NonInteractive", "-Command", script],
                capture_output=True, text=True, timeout=timeout
            )
            return (r.stdout or "").strip()
        except Exception as e:
            log.error(f"PowerShell erro: {e}")
            return ""
