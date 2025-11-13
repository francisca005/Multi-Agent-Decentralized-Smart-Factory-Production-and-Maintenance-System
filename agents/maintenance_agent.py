# agents/maintenance_agent.py
import asyncio
from spade.behaviour import CyclicBehaviour
from agents.base_agent import FactoryAgent
import random

class MaintenanceAgent(FactoryAgent):
    """
    Recebe falhas e agenda reparações.
    Não conclui reparações — isso é feito pelo Environment.
    """

    def __init__(self, jid, password, env):
        super().__init__(jid, password, env=env)
        self.repair_queue = []

    async def receive_failure(self, machine):
        """Chamado quando uma máquina falha."""
        # se já está em reparação → ignora duplicado
        if getattr(machine, "repair_ticks_remaining", 0) > 0:
            await self.log(
                f"[MAINTENANCE] {machine.agent_name} já está em reparação. Ignorado."
            )
            return

        # se já está falhada e não reparada, ok
        machine.is_failed = True

        await self.log(f"[MAINTENANCE] Falha recebida de {machine.agent_name}.")
        self.repair_queue.append(machine)
        self.env.metrics["repairs_started"] += 1



    class RepairHandler(CyclicBehaviour):
        async def run(self):
            # Se há reparações por iniciar
            if self.agent.repair_queue:
                machine = self.agent.repair_queue.pop(0)

                # Escolher tempo de reparação
                repair_time = random.randint(3, 8)
                machine.repair_ticks_remaining = repair_time
                machine.is_failed = True  # garantir estado consistente


                await self.agent.log(
                    f"[MAINTENANCE] Reparação iniciada para {machine.agent_name} "
                    f"({repair_time} ticks)."
                )

            await asyncio.sleep(1)

    async def setup(self):
        self.env.set_maintenance_agent(self)
        await self.log("MaintenanceAgent ativo e pronto.")
        self.add_behaviour(self.RepairHandler())

