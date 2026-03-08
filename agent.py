if __name__ == "__main__":
    import sys

    if "--install" in sys.argv:
        _instalar_servico()
    elif "--uninstall" in sys.argv:
        _desinstalar_servico()
    else:
        NVCloudAgent().start()


def _instalar_servico():
    """Instala e inicia o agente como serviço do Windows"""
    import subprocess, os
    exe = sys.executable if sys.executable.endswith(".exe") else sys.argv[0]
    exe_path = os.path.abspath(exe)

    # Criar serviço
    subprocess.run([
        "sc", "create", "NVCloudAgent",
        "binPath=", f'"{exe_path}"',
        "start=", "auto",
        "DisplayName=", "NVCloud Agent"
    ], check=True)

    # Descrição do serviço
    subprocess.run([
        "sc", "description", "NVCloudAgent",
        "Agente de monitoramento NVCloud RMM"
    ])

    # Iniciar imediatamente
    subprocess.run(["sc", "start", "NVCloudAgent"])

    print("NVCloud Agent instalado e iniciado como serviço!")


def _desinstalar_servico():
    """Remove o serviço do Windows"""
    import subprocess
    subprocess.run(["sc", "stop", "NVCloudAgent"], capture_output=True)
    subprocess.run(["sc", "delete", "NVCloudAgent"])
    print("NVCloud Agent removido!")
