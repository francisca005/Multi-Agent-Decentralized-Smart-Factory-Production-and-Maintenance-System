# agents/supply_cnp_agent.py
import asyncio
import random
from spade.behaviour import CyclicBehaviour
from agents.base_agent import FactoryAgent

def parse_batch_from_body(body: str) -> dict:
    # formato: "ingredients: flour=10, sugar=5, butter=3"
    body = (body or "").lower().replace("ingredients:", "").strip()
    parts = [p.strip() for p in body.split(",") if p.strip()]
    res = {"flour": 0, "sugar": 0, "butter": 0}
    for p in parts:
        if "=" in p:
            k, v = p.split("=", 1)
            k = k.strip()
            try:
                res[k] = int(v)
            except:
                pass
    return res

class SupplyCNPAgent(FactoryAgent):
    """
    Fornecedor 'participant' no CNP.
    - Recebe CFP (call for proposals) com pedido de ingredientes.
    - Se consegue entregar, envia PROPOSE com 'offer': tempo_estimado e um 'cost'.
    - Caso contrário, envia REFUSE.
    - Se receber ACCEPT-PROPOSAL, faz a entrega (INFORM) e atualiza stock.
    - Se receber REJECT-PROPOSAL, ignora.
    """
    def __init__(self, jid, password, *, name="A", initial_stock=None, capacity_per_order=None):
        super().__init__(jid, password)
        self.agent_name = name  
        self.stock = initial_stock or {"flour": 50, "sugar": 30, "butter": 20}
        self.capacity_per_order = capacity_per_order or {"flour": 50, "sugar": 30, "butter": 20}

    def can_fulfill(self, batch: dict) -> bool:
        return all(self.stock.get(k, 0) >= batch.get(k, 0) for k in ["flour", "sugar", "butter"])

    def estimate_offer(self, batch: dict) -> tuple[int, int]:
        """
        Estima (lead_time, cost).
        Exemplo simples:
          - lead_time ~ rand(1..5) - bónus se stock estiver muito folgado
          - cost ~ soma(batch) + ruído
        """
        base_time = random.randint(1, 5)
        # stock folgado reduz um pouco o tempo
        slack = min(self.stock["flour"], self.stock["sugar"], self.stock["butter"])
        if slack > 40:
            base_time = max(1, base_time - 1)

        cost = batch["flour"] + batch["sugar"] + batch["butter"] + random.randint(0, 3)
        return base_time, cost

    class Participant(CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=1)
            if not msg:
                await asyncio.sleep(0.2)
                return

            proto = msg.get_metadata("protocol")
            perf = msg.get_metadata("performative")

            # 1) Recebe CFP → decide PROPOSE ou REFUSE
            if proto == "cnp" and perf == "cfp":
                batch = parse_batch_from_body(msg.body)
                if self.agent.can_fulfill(batch):
                    lead_time, cost = self.agent.estimate_offer(batch)
                    reply = msg.make_reply()
                    reply.set_metadata("protocol", "cnp")
                    reply.set_metadata("performative", "propose")
                    reply.body = f"offer: lead_time={lead_time}; cost={cost}; batch={batch}"
                    await self.send(reply)
                    await self.agent.log(f"[CNP/{self.agent.agent_name}] PROPOSE lead_time={lead_time}, cost={cost}, batch={batch}")
                else:
                    reply = msg.make_reply()
                    reply.set_metadata("protocol", "cnp")
                    reply.set_metadata("performative", "refuse")
                    reply.body = "insufficient_stock"
                    await self.send(reply)
                    await self.agent.log(f"[CNP/{self.agent.agent_name}] REFUSE (insufficient_stock)")

            # 2) Recebe ACCEPT-PROPOSAL → entrega (INFORM)
            elif proto == "cnp" and perf == "accept-proposal":
                batch = parse_batch_from_body(msg.body)
                # entrega: debita stock e "demora" simbólica proporcional ao lead_time (se vier no corpo)
                lead_time = 1
                if "lead_time=" in (msg.body or ""):
                    try:
                        frag = msg.body.split("lead_time=")[1]
                        lead_time = int(frag.split(";")[0].strip())
                    except:
                        pass

                await asyncio.sleep(lead_time)  # simula entrega
                # debita stock (com clamp por segurança)
                for k in ["flour", "sugar", "butter"]:
                    self.agent.stock[k] = max(0, self.agent.stock[k] - batch[k])

                # responde com INFORM
                done = msg.make_reply()
                done.set_metadata("protocol", "cnp")
                done.set_metadata("performative", "inform")
                done.body = f"delivered: {batch} | supplier={self.agent.agent_name} | lead_time={lead_time}"
                await self.send(done)
                await self.agent.log(f"[CNP/{self.agent.agent_name}] INFORM (delivered) | stock={self.agent.stock}")

            # 3) Recebe REJECT-PROPOSAL → nada a fazer
            elif proto == "cnp" and perf == "reject-proposal":
                await self.agent.log(f"[CNP/{self.agent.agent_name}] REJECT-PROPOSAL recebido. (ignora)")

    async def setup(self):
        await self.log(f"(CNP Participant {self.agent_name}) stock inicial={self.stock} cap/pedido={self.capacity_per_order}")
        self.add_behaviour(self.Participant())
