# -*- coding: utf-8 -*-
import random
import asyncio

class FactoryEnvironment:
    """
    Ambiente da Fábrica:
    - Mantém o tempo global (ticks)
    - Regista métricas e falhas
    - Coordena agentes registados e manutenção
    """

    def __init__(self):
        self.time = 0
        self.metrics = {
            "requests_ok": 0,
            "requests_refused": 0,
            "delivered_flour": 0,
            "delivered_sugar": 0,
            "delivered_butter": 0,
            "machine_failures": 0,
            "repairs_started": 0,
            "repairs_finished": 0,
            "machine_downtime_ticks": 0,
            "cnp_cfp": 0,
            "cnp_accepts": 0,
            "jobs_completed": 0,
        }
        self.agents = []
        self.maintenance_agent = None   # referência global ao MaintenanceAgent
        self.external_failure_rate = 0.0  # falhas adicionais (pode ser 0)

    # ------------------------------------------------------
    # Gestão de agentes e manutenção
    # ------------------------------------------------------
    def register_agent(self, agent):
        """Regista um agente no ambiente (máquina, fornecedor, etc.)."""
        self.agents.append(agent)

    def set_maintenance_agent(self, agent):
        """Define o agente de manutenção global."""
        self.maintenance_agent = agent

    # ------------------------------------------------------
    # Ciclo temporal (tick)
    # ------------------------------------------------------
    async def tick(self):
        """Avança um tick no tempo, regista métricas e verifica falhas."""
        self.time += 1

        # Atualiza métricas de downtime
        for a in self.agents:
            if getattr(a, "is_failed", False):
                self.metrics["machine_downtime_ticks"] += 1

        # Simular falhas externas (opcional)
        if self.external_failure_rate > 0:
            for agent in self.agents:
                if getattr(agent, "is_machine", False) and not agent.is_failed:
                    if random.random() < self.external_failure_rate:
                        agent.is_failed = True
                        self.metrics["machine_failures"] += 1
                        if self.maintenance_agent:
                            await self.maintenance_agent.receive_failure(agent)
                        await agent.log(f"[FAILURE] {agent.agent_name} falhou (detetado pelo ambiente).")

        await asyncio.sleep(0.1)  # pequena pausa simbólica (tempo de simulação)



