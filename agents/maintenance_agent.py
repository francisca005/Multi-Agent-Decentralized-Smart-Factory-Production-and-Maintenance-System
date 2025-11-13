import asyncio
from spade.behaviour import CyclicBehaviour
from spade.message import Message
from agents.base_agent import FactoryAgent
import random

class MaintenanceAgent(FactoryAgent):
    """
    Reage a falhas de máquinas e realiza reparações após um tempo aleatório.
    """
    def __init__(self, jid, password, env):
        super().__init__(jid, password, env=env)
        self.repair_queue = []

    async def receive_failure(self, machine):
        """Chamado pelo Environment quando uma máquina falha."""
        await self.log(f"[MAINTENANCE] Falha recebida de {machine.name}.")
        self.repair_queue.append(machine)
        self.env.metrics["repairs_started"] += 1

    class RepairHandler(CyclicBehaviour):
        async def run(self):
            if self.agent.repair_queue:
                machine = self.agent.repair_queue.pop(0)
                repair_time = random.randint(3, 8)
                machine.repair_time_remaining = repair_time
                await self.agent.log(f"[MAINTENANCE] Iniciada reparação de {machine.name} ({repair_time} ticks estimados).")
            await asyncio.sleep(1)

    async def setup(self):
        self.env.set_maintenance_agent(self)
        await self.log("MaintenanceAgent ativo e pronto.")
        self.add_behaviour(self.RepairHandler())
