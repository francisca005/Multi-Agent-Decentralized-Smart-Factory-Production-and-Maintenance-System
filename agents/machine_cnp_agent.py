# agents/machine_cnp_agent.py
import asyncio
from spade.behaviour import CyclicBehaviour
from agents.base_agent import FactoryAgent

def build_batch_str(batch: dict) -> str:
    return f"ingredients: flour={batch['flour']}, sugar={batch['sugar']}, butter={batch['butter']}"

class MachineCNPAgent(FactoryAgent):
    """
    Initiator do Contract Net:
      1) envia CFP para todos os suppliers
      2) recolhe PROPOSE/REFUSE até timeout
      3) seleciona melhor proposta (lead_time -> custo como desempate)
      4) envia ACCEPT ao vencedor e REJECT aos restantes
      5) espera INFORM do vencedor e atualiza métricas / estado local
    """
    def __init__(self, jid, password, *, supplier_jids, request_batch=None, cfp_timeout=3, inform_timeout=10):
        super().__init__(jid, password)
        self.supplier_jids = supplier_jids
        self.request_batch = request_batch or {"flour": 10, "sugar": 5, "butter": 3}
        self.cfp_timeout = cfp_timeout
        self.inform_timeout = inform_timeout

    class Initiator(CyclicBehaviour):
        async def run(self):
            # 1) CFP para todos
            body = build_batch_str(self.agent.request_batch)
            for to_jid in self.agent.supplier_jids:
                msg = self.agent.create_message(
                    to_jid=to_jid,
                    body=body,
                    performative="cfp",
                    protocol="cnp",
                )
                await self.send(msg)
            self.agent.env.metrics["cnp_cfp"] += 1
            await self.agent.log(f"[CNP] CFP enviado a {len(self.agent.supplier_jids)} suppliers: {body}")

            # 2) recolher propostas
            proposals = []  # cada item: (from_jid, lead_time:int, cost:int)
            repliers = set()
            end_time = self.agent.env.time + self.agent.cfp_timeout
            while self.agent.env.time < end_time:
                reply = await self.receive(timeout=0.3)
                if not reply:
                    continue
                if reply.get_metadata("protocol") != "cnp":
                    continue

                perf = reply.get_metadata("performative")
                repliers.add(str(reply.sender))
                if perf == "propose":
                    # parse lead_time e cost do body
                    lead_time, cost = 999, 999
                    try:
                        frag = (reply.body or "")
                        # "offer: lead_time=3; cost=12; batch={...}"
                        lpart = frag.split("lead_time=")[1]
                        lead_time = int(lpart.split(";")[0].strip())
                        cpart = frag.split("cost=")[1]
                        cost = int(cpart.split(";")[0].strip())
                    except:
                        pass
                    proposals.append((str(reply.sender), lead_time, cost))
                    self.agent.env.metrics["cnp_proposals"] += 1
                    await self.agent.log(f"[CNP] PROPOSE de {reply.sender}: lead_time={lead_time}, cost={cost}")

                elif perf == "refuse":
                    await self.agent.log(f"[CNP] REFUSE de {reply.sender}: {reply.body}")

            if not proposals:
                await self.agent.log("[CNP] Sem propostas. Vai tentar de novo mais tarde.")
                await asyncio.sleep(2)
                return

            # 3) selecionar melhor (min lead_time, depois min cost)
            proposals.sort(key=lambda x: (x[1], x[2]))
            winner, win_time, win_cost = proposals[0]
            losers = [jid for (jid, _, _) in proposals[1:]]
            await self.agent.log(f"[CNP] VENCEDOR: {winner} (lead_time={win_time}, cost={win_cost}). Losers={len(losers)}")

            # 4) enviar ACCEPT ao vencedor e REJECT aos restantes
            batch_str = build_batch_str(self.agent.request_batch)
            # inclui lead_time no corpo para o supplier poder simular entrega
            accept = self.agent.create_message(
                to_jid=winner,
                body=f"{batch_str}; lead_time={win_time}",
                performative="accept-proposal",
                protocol="cnp",
            )
            await self.send(accept)
            self.agent.env.metrics["cnp_accepts"] += 1

            for l in losers:
                reject = self.agent.create_message(
                    to_jid=l,
                    body=batch_str,
                    performative="reject-proposal",
                    protocol="cnp",
                )
                await self.send(reject)
                self.agent.env.metrics["cnp_rejects"] += 1

            # 5) aguardar INFORM do vencedor
            informed = False
            end_info = self.agent.env.time + self.agent.inform_timeout
            while self.agent.env.time < end_info:
                inf = await self.receive(timeout=0.5)
                if inf and inf.get_metadata("protocol") == "cnp" and inf.get_metadata("performative") == "inform":
                    await self.agent.log(f"[CNP] INFORM do vencedor: {inf.body}")
                    # atualizar métricas globais (opcional: também stock local se quiseres)
                    batch = self.agent.request_batch
                    self.agent.env.metrics["requests_ok"] += 1
                    self.agent.env.metrics["delivered_flour"] += batch["flour"]
                    self.agent.env.metrics["delivered_sugar"] += batch["sugar"]
                    self.agent.env.metrics["delivered_butter"] += batch["butter"]
                    # contagem por fornecedor (A/B)
                    if "@a" in winner or "suppliera" in winner:
                        self.agent.env.metrics["cnp_wins_supplier_a"] += 1
                    else:
                        self.agent.env.metrics["cnp_wins_supplier_b"] += 1

                    informed = True
                    break

            if not informed:
                await self.agent.log("[CNP] Timeout à espera do INFORM do vencedor.")

            await asyncio.sleep(2)  # espaçar rondas de CNP

    async def setup(self):
        await self.log(f"(CNP Initiator) suppliers={self.supplier_jids} | batch={self.request_batch} | timeout(CFP)={self.cfp_timeout}s")
        self.add_behaviour(self.Initiator())
