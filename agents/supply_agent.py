# agents/supply_agent.py
import asyncio
from spade.behaviour import CyclicBehaviour
from agents.base_agent import FactoryAgent

def parse_request(body: str):
    """
    Extrai quantities do formato: 'ingredients: flour=10, sugar=5, butter=3'
    """
    wanted = {"flour": 0, "sugar": 0, "butter": 0}
    txt = body.lower()
    for k in wanted:
        if f"{k}=" in txt:
            try:
                part = txt.split(f"{k}=")[1].split(",")[0]
                wanted[k] = int(part.strip())
            except Exception:
                wanted[k] = 0
    return wanted

class SupplyAgent(FactoryAgent):
    """
    Responde a pedidos de materiais. Mantém stock e capacidade por pedido.
    """
    def __init__(self, jid, password, *, capacity_per_order=None, initial_stock=None):
        super().__init__(jid, password)
        self.capacity_per_order = capacity_per_order or {"flour": 50, "sugar": 30, "butter": 20}
        self.stock = initial_stock or {"flour": 100, "sugar": 60, "butter": 40}

    class Responder(CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=5)
            if not msg:
                await asyncio.sleep(0.5)
                return

            await self.agent.log(f"REQUEST de {msg.sender}: {msg.body}")
            wanted = parse_request(msg.body)

            # verifica capacidade por pedido (limite operacional)
            for k, v in wanted.items():
                if v > self.agent.capacity_per_order.get(k, 0):
                    reply = msg.make_reply()
                    reply.set_metadata("performative", "refuse")
                    reply.set_metadata("protocol", "fipa-request")
                    reply.body = f"cap_exceeded: {k}={v} > cap={self.agent.capacity_per_order[k]}"
                    await self.send(reply)
                    await self.agent.log(f"REFUSE (capacidade excedida em {k}).")
                    self.agent.env.metrics["requests_refused"] += 1
                    return

            # verifica stock suficiente
            possible = all(self.agent.stock.get(k, 0) >= wanted[k] for k in wanted)
            if not possible:
                reply = msg.make_reply()
                reply.set_metadata("performative", "refuse")
                reply.set_metadata("protocol", "fipa-request")
                reply.body = "stock_insufficient"
                await self.send(reply)
                await self.agent.log("REFUSE (stock insuficiente).")
                self.agent.env.metrics["requests_refused"] += 1
                return

            # faz a entrega
            for k in wanted:
                self.agent.stock[k] -= wanted[k]
            self.agent.env.metrics["requests_ok"] += 1
            self.agent.env.metrics["delivered_flour"] += wanted["flour"]
            self.agent.env.metrics["delivered_sugar"] += wanted["sugar"]
            self.agent.env.metrics["delivered_butter"] += wanted["butter"]

            reply = msg.make_reply()
            reply.set_metadata("performative", "inform")
            reply.set_metadata("protocol", "fipa-request")
            reply.body = f"delivered: {wanted} | stock_now: {self.agent.stock}"
            await self.send(reply)
            await self.agent.log(f"INFORM enviado. Stock agora: {self.agent.stock}")

    async def setup(self):
        await self.log(f"(Responder) stock inicial: {self.stock} | cap/pedido: {self.capacity_per_order}")
        self.add_behaviour(self.Responder())



