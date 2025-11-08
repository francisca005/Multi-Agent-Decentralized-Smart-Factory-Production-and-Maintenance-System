# agents/machine_agent.py
import asyncio
import random
from spade.behaviour import CyclicBehaviour
from agents.base_agent import FactoryAgent


class MachineAgent(FactoryAgent):
    """
    Máquina de produção com falhas aleatórias.
    Estados:
      - status = 'working' | 'faulty'
    Quando 'faulty', pede reparação ao MaintenanceAgent e aguarda confirmação.
    """
    def __init__(self, jid, password, target_jid, *,
                 maintenance_jid=None,
                 local_stock=None, thresholds=None, request_batch=None,
                 failure_rate=0.05):  # probabilidade de avaria por ciclo
        super().__init__(jid, password)
        self.target_jid = target_jid
        self.maintenance_jid = maintenance_jid
        self.local_stock = local_stock or {"flour": 0, "sugar": 0, "butter": 0}
        self.thresholds = thresholds or {"flour": 15, "sugar": 10, "butter": 6}
        self.request_batch = request_batch or {"flour": 10, "sugar": 5, "butter": 3}
        self.failure_rate = failure_rate
        self.status = "working"
        self.waiting_repair = False  # para não reenviar pedidos em loop

    def needs_restock(self):
        return any(self.local_stock[k] < self.thresholds[k] for k in self.local_stock)

    def build_request_body(self):
        return f"ingredients: flour={self.request_batch['flour']}, sugar={self.request_batch['sugar']}, butter={self.request_batch['butter']}"

    def _maybe_fail(self):
        if self.status == "working" and random.random() < self.failure_rate:
            self.status = "faulty"
            self.env.metrics["machine_failures"] += 1

    class Producer(CyclicBehaviour):
        async def run(self):
            # falhas e downtime
            if self.agent.status == "faulty":
                self.agent.env.metrics["machine_downtime_ticks"] += 1
                # já pediu reparo?
                if self.agent.maintenance_jid and not self.agent.waiting_repair:
                    # envia pedido de reparo
                    msg = self.agent.create_message(
                        to_jid=self.agent.maintenance_jid,
                        body=f"repair_request:{self.agent.jid}",
                        performative="request",
                        protocol="maintenance",
                    )
                    await self.send(msg)
                    self.agent.waiting_repair = True
                    await self.agent.log("AVARIA! Repair request enviado ao MaintenanceAgent.")
                else:
                    # à espera...
                    pass

                # ver respostas de manutenção
                reply = await self.receive(timeout=0.2)
                if reply and reply.get_metadata("protocol") == "maintenance":
                    perf = reply.get_metadata("performative")
                    if perf == "agree":
                        await self.agent.log(f"Maintenance AGREE: {reply.body}")
                    elif perf == "refuse":
                        await self.agent.log("Maintenance REFUSE (ocupado). Vai tentar de novo em breve.")
                        self.agent.waiting_repair = False
                    elif perf == "inform" and (reply.body or "").strip().lower() == "repair_done":
                        await self.agent.log("Maintenance INFORM: repair_done. Retomando produção.")
                        self.agent.status = "working"
                        self.agent.waiting_repair = False
                await asyncio.sleep(1)
                return  # enquanto avariada, não produz nem pede materiais

            # estado 'working': consumo simples e restock
            for k in self.agent.local_stock:
                if self.agent.local_stock[k] > 0:
                    self.agent.local_stock[k] -= 1

            if self.agent.needs_restock():
                body = self.agent.build_request_body()
                msg = self.agent.create_message(
                    to_jid=self.agent.target_jid,
                    body=body,
                    performative="request",
                    protocol="fipa-request",
                )
                await self.send(msg)
                await self.agent.log(f"REQUEST enviado a {self.agent.target_jid}: {body}")

                reply = await self.receive(timeout=8)
                if reply and reply.get_metadata("performative") == "inform":
                    # atualização simples pelo batch
                    for k, v in self.agent.request_batch.items():
                        self.agent.local_stock[k] += v
                    await self.agent.log(f"INFORM recebido: {reply.body} | local_stock={self.agent.local_stock}")
                elif reply and reply.get_metadata("performative") == "refuse":
                    await self.agent.log(f"REFUSE recebido: {reply.body} (vai tentar mais tarde)")
                else:
                    await self.agent.log("Timeout à espera de resposta do fornecedor.")

            # probabilidade de falhar no fim do ciclo
            self.agent._maybe_fail()

            await asyncio.sleep(2)

    async def setup(self):
        await self.log(f"(Requester+Failures) local_stock={self.local_stock} | thresholds={self.thresholds} | batch={self.request_batch} | failure_rate={self.failure_rate}")
        self.add_behaviour(self.Producer())



