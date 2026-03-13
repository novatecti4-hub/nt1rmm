#!/usr/bin/env python3
"""
tray.py — Wrapper que expõe a classe TrayApp para ser importada pelo agent.py

O agent.py faz: from tray import TrayApp
Este arquivo conecta o agent ao nvcloud_tray.py
"""
import threading
import logging

log = logging.getLogger("tray")


class TrayApp:
    """
    Gerencia o ícone na bandeja do sistema e as notificações do Shield.
    Instanciado pelo NVCloudAgent apenas quando há interface gráfica disponível.
    """

    def __init__(self, agent):
        self.agent = agent

    def iniciar(self):
        """
        Inicia o ícone de bandeja e o loop de verificação do Shield.
        Bloqueia até o usuário clicar em 'Sair' no menu da bandeja.
        """
        try:
            import pystray
        except ImportError:
            log.error("pystray não instalado — tray não disponível")
            return

        # Importa funções do módulo principal do tray
        from nvcloud_tray import (
            Api, shield_loop, criar_icone, build_menu, load_config
        )

        try:
            cfg = load_config()
        except SystemExit:
            log.error("config.json não encontrado — tray não iniciado")
            return

        token    = cfg.get("token", "")
        sup_url  = cfg.get("supabase_url", "")
        app_url  = cfg.get("app_url", "https://tech-guard-flow.lovable.app")
        agent_id = cfg.get("agent_id", "")

        # Se não tiver agent_id no config, tenta pegar do objeto agent
        if not agent_id and hasattr(self.agent, "cfg"):
            agent_id = getattr(self.agent.cfg, "agent_id", "")

        if not token or not sup_url:
            log.error("token ou supabase_url ausentes no config — tray não iniciado")
            return

        api        = Api(sup_url, token)
        stop_event = threading.Event()
        icon_ref   = []

        # Loop do Shield em background (verifica campanhas a cada 30 min)
        t = threading.Thread(
            target=shield_loop,
            args=(api, app_url, stop_event, agent_id),
            daemon=True
        )
        t.start()
        log.info(f"Shield loop iniciado para agent_id={agent_id or '(resolver via JWT)'}")

        # Cria e exibe ícone na bandeja — CORRIGIDO: passa api e agent_id
        imagem = criar_icone()
        menu   = build_menu(api, app_url, agent_id, stop_event, icon_ref)
        icon   = pystray.Icon("NVCloud", imagem, "NVCloud Agent", menu)
        icon_ref.append(icon)

        log.info("Tray iniciado com sucesso")
        # run_detached permite que o ícone apareça mesmo via Task Scheduler
        if hasattr(icon, 'run_detached'):
            icon.run_detached()
            # Mantém o processo vivo
            while not stop_event.is_set():
                import time
                time.sleep(1)
        else:
            icon.run()  # fallback
