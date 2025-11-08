# agents/maintenance_agent.py
import asyncio
from spade.behaviour import CyclicBehaviour
from agents.base_agent import FactoryAgent


class MaintenanceAgent(FactoryAgent):
    """
    Agente de manutenção com capacidade 1 (FIFO).
    Recebe pedidos "repair_request:<jid>" e responde:
      - 'agree' quando aceita
      - 'inform' quando termina a reparação após repair_time ticks/segundos simulados.
    """
    def __init__(self, jid, password, *, repair_time=5):
        super().__init__(jid, password)
        self.repair_time = repair_time
        self._busy = False

    class Dispatcher(CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=1)
            if not msg:
                await asyncio.sleep(0.2)
                return

            body = (msg.body or "").strip().lower()
            if not body.startswith("repair_request"):
                await self.agent.log(f"Mensagem ignorada: {body}")
                return

            # já ocupado?
            if self.agent._busy:
                # simples recusa se ocupado; poderias pôr numa fila
                reply = msg.make_reply()
                reply.set_metadata("performative", "refuse")
                reply.set_metadata("protocol", "maintenance")
                reply.body = "busy"
                await self.send(reply)
                await self.agent.log("REFUSE enviado (busy).")
                return

            # aceita
            self.agent._busy = True
            self.agent.env.metrics["repairs_started"] += 1
            reply = msg.make_reply()
            reply.set_metadata("performative", "agree")
            reply.set_metadata("protocol", "maintenance")
            reply.body = f"accepted: will repair in {self.agent.repair_time}s"
            await self.send(reply)
            await self.agent.log(f"AGREE enviado. A reparar por {self.agent.repair_time}s...")

            # simula tempo de reparo
            await asyncio.sleep(self.agent.repair_time)

            # termina
            done = msg.make_reply()
            done.set_metadata("performative", "inform")
            done.set_metadata("protocol", "maintenance")
            done.body = "repair_done"
            await self.send(done)
            self.agent.env.metrics["repairs_finished"] += 1
            self.agent._busy = False
            await self.agent.log("INFORM enviado (repair_done).")

    async def setup(self):
        await self.log(f"iniciado. repair_time={self.repair_time}s, cap=1")
        self.add_behaviour(self.Dispatcher())
