# -*- coding: utf-8 -*-
import asyncio
from spade.behaviour import CyclicBehaviour
from agents.base_agent import FactoryAgent

class SupervisorAgent(FactoryAgent):
    """
    Agente Supervisor:
    - Executa o ciclo de tempo global (tick do ambiente).
    - Efetua reabastecimento periódico de um fornecedor (stock refill).
    - Regista métricas e estado geral do sistema.
    """

    def __init__(self, jid, password, env=None,
                 supply_refill_every=10, refill_amount=None, supply_agent_ref=None):
        super().__init__(jid, password, env)
        self.supply_refill_every = supply_refill_every
        self.refill_amount = refill_amount or {"flour": 40, "sugar": 20, "butter": 12}
        self.supply_agent_ref = supply_agent_ref

    class Ticker(CyclicBehaviour):
        async def run(self):
            agent = self.agent
            env = agent.env

            # ✅ Corrigido: tick é uma coroutine assíncrona
            await env.tick()
            t = env.time

            # 🧺 Refill periódico de fornecedor
            if agent.supply_agent_ref and t % agent.supply_refill_every == 0:
                for k, v in agent.refill_amount.items():
                    agent.supply_agent_ref.stock[k] += v
                await agent.log(
                    f"[t={t}] Refill fornecedor: +{agent.refill_amount} | "
                    f"stock fornecedor={agent.supply_agent_ref.stock}"
                )

            # 📊 Métricas simplificadas e relevantes
            if t % 5 == 0:
                m = env.metrics
                await agent.log(
                    f"[t={t}] metrics: "
                    f"failures={m['machine_failures']}, "
                    f"repairs_started={m['repairs_started']}, "
                    f"repairs_finished={m['repairs_finished']}, "
                    f"downtime_ticks={m['machine_downtime_ticks']}, "
                    f"cnp_cfp={m['cnp_cfp']}, "
                    f"cnp_accepts={m['cnp_accepts']}"
                )

            # ⏳ Espera entre ticks
            await asyncio.sleep(1)

    async def setup(self):
        """Inicializa o supervisor e inicia o comportamento periódico."""
        await self.log(
            f"iniciado. refill_cada={self.supply_refill_every} ticks | "
            f"refill={self.refill_amount}"
        )
        self.add_behaviour(self.Ticker())



