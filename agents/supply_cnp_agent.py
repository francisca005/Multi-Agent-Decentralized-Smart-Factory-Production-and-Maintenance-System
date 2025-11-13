# agents/supply_cnp_agent.py
from agents.base_agent import FactoryAgent
from spade.behaviour import CyclicBehaviour
from spade.message import Message
import random

class SupplyCNPAgent(FactoryAgent):
    def __init__(self, jid, password, env=None, name="Supplier",
                 stock_init=None, capacity=None):
        super().__init__(jid, password, env)
        self.agent_name = name
        self.stock = stock_init or {"flour": 50, "sugar": 30, "butter": 20}
        self.capacity = capacity or {"flour": 50, "sugar": 30, "butter": 20}

    async def setup(self):
        await self.log(f"(CNP Participant {self.agent_name}) stock inicial={self.stock} cap/pedido={self.capacity}")
        self.add_behaviour(self.Participant())

    # =============================================================
    #  CNP PARTICIPANT BEHAVIOUR
    # =============================================================
    class Participant(CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=1)
            if not msg:
                return

            pf = msg.metadata.get("performative")
            if pf == "cfp":
                # Decide se aceita participar
                if any(v < 5 for v in self.agent.stock.values()):
                    refuse = Message(to=str(msg.sender))
                    refuse.set_metadata("protocol", "cnp")
                    refuse.set_metadata("performative", "refuse")
                    refuse.body = "insufficient_stock"
                    await self.send(refuse)
                    await self.agent.log(f"[CNP/{self.agent.agent_name}] REFUSE (insufficient_stock)")
                    return

                # Cria proposta
                lead_time = random.randint(2, 6)
                cost = random.randint(15, 22)
                propose = Message(to=str(msg.sender))
                propose.set_metadata("protocol", "cnp")
                propose.set_metadata("performative", "propose")
                propose.body = f"lead_time={lead_time}; cost={cost}; batch={msg.body}"
                await self.send(propose)
                await self.agent.log(f"[CNP/{self.agent.agent_name}] PROPOSE lead_time={lead_time}, cost={cost}, batch={msg.body}")

            elif pf == "accept-proposal":
                # Simula entrega
                for k in self.agent.stock.keys():
                    self.agent.stock[k] = max(0, self.agent.stock[k] - 10)
                inform = Message(to=str(msg.sender))
                inform.set_metadata("protocol", "cnp")
                inform.set_metadata("performative", "inform")
                inform.body = f"delivered: {msg.body} | stock={self.agent.stock}"
                await self.send(inform)
                await self.agent.log(f"[CNP/{self.agent.agent_name}] INFORM (delivered) | stock={self.agent.stock}")

            elif pf == "reject-proposal":
                await self.agent.log(f"[CNP/{self.agent.agent_name}] REJECT-PROPOSAL recebido. (ignora)")

