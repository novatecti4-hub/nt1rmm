"""
modules/ailocal.py — Análise local de métricas com detecção de anomalias.

Monitora CPU, RAM, disco, temperatura e rede.
Gera insights enviados junto com as métricas para o painel.
"""
from collections import deque
from dataclasses import dataclass
from typing import List, Optional, Dict
from datetime import datetime, timezone
import logging

log = logging.getLogger("ailocal")


@dataclass
class Insight:
    tipo: str           # "alerta" | "tendencia" | "critico" | "info"
    metrica: str        # "cpu" | "ram" | "disco" | "temp" | "rede"
    mensagem: str
    severidade: str     # "critico" | "aviso" | "info"
    projecao_dias: Optional[int] = None
    valor_atual: Optional[float] = None
    valor_limite: Optional[float] = None


class LocalAIAnalyzer:
    """
    Analisa amostras de métricas coletadas a cada 5 minutos.
    Janela padrão: 288 amostras = 24 horas.
    """

    def __init__(self, max_samples: int = 288):
        self.cpu_samples:  deque = deque(maxlen=max_samples)
        self.ram_samples:  deque = deque(maxlen=max_samples)
        self.temp_samples: deque = deque(maxlen=max_samples)
        self.disco_samples: Dict[str, deque] = {}
        self.rede_sent_mbps: deque = deque(maxlen=max_samples)
        self.rede_recv_mbps: deque = deque(maxlen=max_samples)
        self._rede_prev_sent: Optional[int] = None
        self._rede_prev_recv: Optional[int] = None
        self._rede_prev_ts:   Optional[float] = None
        self._max_samples = max_samples

    def add_sample(self, metrics: dict) -> List[Insight]:
        """
        Recebe um snapshot de métricas e retorna lista de insights.
        Chamado pelo MetricsModule a cada coleta.
        """
        self._coletar_cpu(metrics)
        self._coletar_ram(metrics)
        self._coletar_temp(metrics)
        self._coletar_disco(metrics)
        self._coletar_rede(metrics)

        # Espera pelo menos 1 hora de dados antes de gerar alertas
        if len(self.cpu_samples) < 12:
            return []

        insights = []
        insights += self._analisar_cpu()
        insights += self._analisar_ram()
        insights += self._analisar_temp()
        insights += self._analisar_disco()
        insights += self._analisar_rede()

        if insights:
            log.info(f"AI Local: {len(insights)} insight(s) gerado(s)")

        return insights

    # ──────────────────────────────────────────────
    # Coleta de amostras
    # ──────────────────────────────────────────────
    def _coletar_cpu(self, m: dict):
        v = m.get("cpu_uso")
        if v is not None:
            self.cpu_samples.append(float(v))

    def _coletar_ram(self, m: dict):
        v = m.get("ram_uso_pct")
        if v is not None:
            self.ram_samples.append(float(v))

    def _coletar_temp(self, m: dict):
        v = m.get("cpu_temp")
        if v is not None:
            self.temp_samples.append(float(v))

    def _coletar_disco(self, m: dict):
        for d in m.get("disco_json", []):
            mp  = d.get("mountpoint", "")
            pct = d.get("uso_pct")
            if mp and pct is not None:
                if mp not in self.disco_samples:
                    self.disco_samples[mp] = deque(maxlen=self._max_samples)
                self.disco_samples[mp].append(float(pct))

    def _coletar_rede(self, m: dict):
        rede = m.get("rede_json", {})
        sent = rede.get("bytes_sent")
        recv = rede.get("bytes_recv")
        now  = datetime.now(timezone.utc).timestamp()
        if sent is not None and recv is not None:
            if self._rede_prev_sent is not None:
                dt = now - self._rede_prev_ts
                if dt > 0:
                    s = (sent - self._rede_prev_sent) / dt / 1_000_000 * 8
                    r = (recv - self._rede_prev_recv) / dt / 1_000_000 * 8
                    self.rede_sent_mbps.append(max(0.0, s))
                    self.rede_recv_mbps.append(max(0.0, r))
            self._rede_prev_sent = sent
            self._rede_prev_recv = recv
            self._rede_prev_ts   = now

    # ──────────────────────────────────────────────
    # Análise CPU
    # ──────────────────────────────────────────────
    def _analisar_cpu(self) -> List[Insight]:
        insights = []
        lst     = list(self.cpu_samples)
        recente = self._media(lst[-12:])

        if recente > 90:
            insights.append(Insight(
                tipo="critico", metrica="cpu",
                mensagem=f"CPU crítica: {recente:.0f}% na última hora",
                severidade="critico",
                valor_atual=recente, valor_limite=90.0
            ))
        elif recente > 80:
            insights.append(Insight(
                tipo="alerta", metrica="cpu",
                mensagem=f"CPU elevada: {recente:.0f}% na última hora",
                severidade="aviso",
                valor_atual=recente, valor_limite=80.0
            ))

        if len(lst) >= 24:
            anterior = self._media(lst[-24:-12])
            if recente > anterior * 1.4 and recente > 60:
                insights.append(Insight(
                    tipo="tendencia", metrica="cpu",
                    mensagem=f"CPU em crescimento: {anterior:.0f}% → {recente:.0f}% na última hora",
                    severidade="aviso", projecao_dias=2, valor_atual=recente
                ))
        return insights

    # ──────────────────────────────────────────────
    # Análise RAM
    # ──────────────────────────────────────────────
    def _analisar_ram(self) -> List[Insight]:
        insights = []
        lst     = list(self.ram_samples)
        recente = self._media(lst[-12:])

        if recente > 95:
            insights.append(Insight(
                tipo="critico", metrica="ram",
                mensagem=f"RAM crítica: {recente:.0f}% — risco de travamento",
                severidade="critico", valor_atual=recente, valor_limite=95.0
            ))
        elif recente > 85:
            insights.append(Insight(
                tipo="alerta", metrica="ram",
                mensagem=f"RAM elevada: {recente:.0f}% na última hora",
                severidade="aviso", valor_atual=recente, valor_limite=85.0
            ))

        # Memory leak — crescimento em 12h
        if len(lst) >= 144:
            inicio = self._media(lst[:24])
            fim    = self._media(lst[-24:])
            if fim > inicio + 15 and fim > 70:
                insights.append(Insight(
                    tipo="tendencia", metrica="ram",
                    mensagem=f"RAM crescendo: {inicio:.0f}% → {fim:.0f}% em 12h. Possível memory leak.",
                    severidade="aviso", projecao_dias=1, valor_atual=fim
                ))
        return insights

    # ──────────────────────────────────────────────
    # Análise Temperatura
    # ──────────────────────────────────────────────
    def _analisar_temp(self) -> List[Insight]:
        insights = []
        if len(self.temp_samples) < 6:
            return insights

        lst     = list(self.temp_samples)
        recente = self._media(lst[-6:])

        if recente > 90:
            insights.append(Insight(
                tipo="critico", metrica="temp",
                mensagem=f"Temperatura crítica: {recente:.0f}°C — risco de desligamento",
                severidade="critico", valor_atual=recente, valor_limite=90.0
            ))
        elif recente > 80:
            insights.append(Insight(
                tipo="alerta", metrica="temp",
                mensagem=f"Temperatura elevada: {recente:.0f}°C — verificar ventilação",
                severidade="aviso", valor_atual=recente, valor_limite=80.0
            ))
        elif recente > 70:
            insights.append(Insight(
                tipo="info", metrica="temp",
                mensagem=f"Temperatura acima do normal: {recente:.0f}°C",
                severidade="info", valor_atual=recente
            ))
        return insights

    # ──────────────────────────────────────────────
    # Análise Disco
    # ──────────────────────────────────────────────
    def _analisar_disco(self) -> List[Insight]:
        insights = []
        for mp, samples in self.disco_samples.items():
            if len(samples) < 2:
                continue
            lst   = list(samples)
            atual = lst[-1]

            if atual >= 95:
                insights.append(Insight(
                    tipo="critico", metrica="disco",
                    mensagem=f"Disco {mp}: {atual:.0f}% — praticamente cheio!",
                    severidade="critico", valor_atual=atual, valor_limite=95.0
                ))
            elif atual >= 85:
                insights.append(Insight(
                    tipo="alerta", metrica="disco",
                    mensagem=f"Disco {mp}: {atual:.0f}% de uso",
                    severidade="aviso", valor_atual=atual, valor_limite=85.0
                ))

            # Projeção de enchimento
            if len(lst) >= 12:
                crescimento = atual - lst[-12]   # variação na última hora
                if crescimento > 2 and atual > 70:
                    livre = 100 - atual
                    if crescimento > 0:
                        dias = int(livre / (crescimento * 24))
                        if dias <= 7:
                            insights.append(Insight(
                                tipo="tendencia", metrica="disco",
                                mensagem=f"Disco {mp} crescendo +{crescimento:.1f}%/h. "
                                         f"Estimativa: {dias}d para encher.",
                                severidade="aviso" if dias > 3 else "critico",
                                projecao_dias=dias, valor_atual=atual
                            ))
        return insights

    # ──────────────────────────────────────────────
    # Análise Rede
    # ──────────────────────────────────────────────
    def _analisar_rede(self) -> List[Insight]:
        insights = []
        if len(self.rede_recv_mbps) < 6:
            return insights

        recente = self._media(list(self.rede_recv_mbps)[-6:])
        if recente > 500:
            insights.append(Insight(
                tipo="alerta", metrica="rede",
                mensagem=f"Tráfego de rede elevado: {recente:.0f} Mbps (download/30min)",
                severidade="aviso", valor_atual=recente
            ))
        return insights

    # ──────────────────────────────────────────────
    # Helper
    # ──────────────────────────────────────────────
    @staticmethod
    def _media(lst: list) -> float:
        return sum(lst) / len(lst) if lst else 0.0
