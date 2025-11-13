# -*- coding: utf-8 -*-
from agents.base_agent import FactoryAgent
from spade.behaviour import CyclicBehaviour
from spade.message import Message
import asyncio
import random


class MachineCNPAgent(FactoryAgent):
    """
    Máquina que inicia CNPs com fornecedores.
    Agora integra falhas, manutenção e espera adaptativa após recusas.
    """

    def __init__(self, jid, password, env=None,
                 suppliers=None, batch=None,
                 cfp_timeout=3, inform_timeout=5, name="Machine",
                 maintenance=None, failure_rate=0.05):
        super().__init__(jid, password, env)
        self.suppliers = suppliers or []
        self.batch = batch or {"flour": 10, "sugar": 5, "butter": 3}
        self.cfp_timeout = cfp_timeout
        self.inform_timeout = inform_timeout
        self.agent_name = name
        self.maintenance = maintenance or (env and getattr(env, "maintenance_agent", None))
        self.failure_rate = failure_rate
        self.is_failed = False
        self.repair_ticks_remaining = 0
        self.is_machine = True

    async def setup(self):
        self.env.register_agent(self)
        await self.log(f"(CNP Initiator {self.agent_name}) suppliers={self.suppliers} | batch={self.batch}")
        self.add_behaviour(self.CNPInitiator())

    # =============================================================
    #  CNP INITIATOR BEHAVIOUR (com falhas e manutenção)
    # =============================================================
    class CNPInitiator(CyclicBehaviour):
        async def run(self):
            agent = self.agent

            # Se está em reparação
            if agent.is_failed:
                agent.env.metrics["machine_downtime_ticks"] += 1
                if agent.repair_ticks_remaining > 0:
                    agent.repair_ticks_remaining -= 1
                    await asyncio.sleep(1)
                    return
                else:
                    agent.is_failed = False
                    agent.repair_ticks_remaining = 0
                    await agent.log(f"[MAINTENANCE] Reparação concluída. Máquina {agent.agent_name} operacional.")
                    agent.env.metrics["repairs_finished"] += 1
                    return  # não faz mais nada neste tick

            # Chance de falha
            if random.random() < agent.failure_rate:
                agent.is_failed = True
                agent.env.metrics["machine_failures"] += 1
                await agent.log(f"[FAILURE] {agent.agent_name} avariou! Notificando MaintenanceAgent...")
                if agent.maintenance:
                    await agent.maintenance.receive_failure(agent)
                return

            # Preparar CFP
            body = f"ingredients: flour={agent.batch['flour']}, sugar={agent.batch['sugar']}, butter={agent.batch['butter']}"
            for supplier in agent.suppliers:
                msg = Message(to=supplier)
                msg.set_metadata("performative", "cfp")
                msg.set_metadata("protocol", "cnp")
                msg.thread = f"cnp-{agent.agent_name}-{agent.env.time}"
                msg.body = body
                await self.send(msg)
                await agent.log(f"[{agent.agent_name}] [CNP] CFP enviado a {supplier}: {msg.body}")
                await asyncio.sleep(0.1)

            agent.env.metrics["cnp_cfp"] += 1
            proposals = []
            end_time = asyncio.get_event_loop().time() + agent.cfp_timeout

            # Aguardar propostas
            while asyncio.get_event_loop().time() < end_time:
                reply = await self.receive(timeout=0.5)
                if reply:
                    pf = reply.metadata.get("performative")
                    if pf == "propose":
                        data = reply.body.split(";")
                        lead_time = int(data[0].split("=")[1])
                        cost = int(data[1].split("=")[1])
                        proposals.append((str(reply.sender), lead_time, cost))
                        await agent.log(f"[CNP] PROPOSE de {reply.sender}: lead_time={lead_time}, cost={cost}")
                    elif pf == "refuse":
                        await agent.log(f"[CNP] REFUSE de {reply.sender}: {reply.body}")

            # Se ninguém propôs
            if not proposals:
                await agent.log("[CNP] Todos os fornecedores recusaram. Aguardando refill de stock...")
                await asyncio.sleep(random.uniform(5, 8))
                return

            # Escolher vencedor (menor custo)
            winner = min(proposals, key=lambda x: x[2])
            losers = [p for p in proposals if p != winner]
            await agent.log(f"[CNP] VENCEDOR: {winner[0]} (lead_time={winner[1]}, cost={winner[2]}). Losers={len(losers)}")

            # Enviar rejeições
            for s, _, _ in losers:
                rej = Message(to=s)
                rej.set_metadata("protocol", "cnp")
                rej.set_metadata("performative", "reject-proposal")
                rej.body = "rejected"
                await self.send(rej)

            # Enviar aceitação
            acc = Message(to=winner[0])
            acc.set_metadata("protocol", "cnp")
            acc.set_metadata("performative", "accept-proposal")
            acc.body = "accepted"
            await self.send(acc)

            # Esperar INFORM
            reply = await self.receive(timeout=agent.inform_timeout)
            if reply and reply.metadata.get("performative") == "inform":
                await agent.log(f"[CNP] INFORM do vencedor: {reply.body}")
                agent.env.metrics["cnp_accepts"] += 1
                agent.env.metrics["jobs_completed"] += 1
            else:
                await agent.log("[CNP] Timeout à espera de INFORM do vencedor")

            # Pausa entre contratos
            await asyncio.sleep(random.uniform(3, 6))



