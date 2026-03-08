from collections import deque
from dataclasses import dataclass
from typing import List, Optional
import logging
log = logging.getLogger("ailocal")

@dataclass
class Insight:
    tipo: str
    metrica: str
    mensagem: str
    severidade: str
    projecao_dias: Optional[int] = None

class LocalAIAnalyzer:
    def __init__(self, max_samples=288):  # 24h com coleta a cada 5min
        self.cpu_samples = deque(maxlen=max_samples)
        self.ram_samples = deque(maxlen=max_samples)

    def add_sample(self, metrics: dict) -> List[Insight]:
        cpu = metrics.get("cpu_uso", 0)
        ram = metrics.get("ram_uso_pct", 0)
        self.cpu_samples.append(cpu)
        self.ram_samples.append(ram)

        if len(self.cpu_samples) < 12:  # aguardar 1h de dados
            return []

        insights = []

        # Tendência CPU
        cpu_list = list(self.cpu_samples)
        recente = sum(cpu_list[-12:]) / 12   # última hora
        anterior = sum(cpu_list[-24:-12]) / 12 if len(cpu_list) >= 24 else recente
        if recente > 80:
            insights.append(Insight("alerta", "cpu",
                f"CPU em {recente:.0f}% na última hora", "critico"))
        elif recente > anterior * 1.3 and recente > 50:
            insights.append(Insight("tendencia", "cpu",
                f"CPU subindo: {anterior:.0f}% → {recente:.0f}%", "aviso",
                projecao_dias=3))

        # Tendência RAM
        ram_list = list(self.ram_samples)
        ram_recente = sum(ram_list[-12:]) / 12
        if ram_recente > 85:
            insights.append(Insight("alerta", "ram",
                f"RAM em {ram_recente:.0f}% na última hora", "critico"))

        return insights
