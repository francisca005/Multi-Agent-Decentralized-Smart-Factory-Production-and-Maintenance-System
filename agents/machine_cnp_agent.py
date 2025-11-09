# agents/machine_cnp_agent.py
from agents.base_agent import FactoryAgent
from spade.behaviour import CyclicBehaviour
from spade.message import Message
import asyncio
import random

class MachineCNPAgent(FactoryAgent):
    def __init__(self, jid, password, env=None,
                 suppliers=None, batch=None,
                 cfp_timeout=3, inform_timeout=5, name="Machine"):
        super().__init__(jid, password, env)
        self.suppliers = suppliers or []
        self.batch = batch or {"flour": 10, "sugar": 5, "butter": 3}
        self.cfp_timeout = cfp_timeout
        self.inform_timeout = inform_timeout
        self.agent_name = name

    async def setup(self):
        await self.log(f"(CNP Initiator {self.agent_name}) suppliers={self.suppliers} | batch={self.batch}")
        self.add_behaviour(self.CNPInitiator())

    # =============================================================
    #  CNP INITIATOR BEHAVIOUR
    # =============================================================
    class CNPInitiator(CyclicBehaviour):
        async def run(self):
            agent = self.agent

            # preparar mensagem CFP
            body = f"ingredients: flour={agent.batch['flour']}, sugar={agent.batch['sugar']}, butter={agent.batch['butter']}"
            msg_template = Message()
            msg_template.set_metadata("protocol", "cnp")
            msg_template.set_metadata("performative", "cfp")

            for supplier in self.agent.suppliers:
                msg = Message(to=supplier)
                msg.set_metadata("performative", "cfp")
                msg.set_metadata("protocol", "cnp")
                msg.thread = f"cnp-{self.agent.name}-{self.agent.env.time}"
                msg.body = body
                await self.send(msg)
                await self.agent.log(f"[{self.agent.name}] [CNP] CFP enviado a {supplier}: {msg.body}")

            # Atualiza métricas globais
            await self.agent.log(f"[{self.agent.name}] [CNP] CFP enviado a {len(self.agent.suppliers)} suppliers: {body}")
            self.agent.env.metrics["cnp_cfp"] += 1

            proposals = []
            end_time = asyncio.get_event_loop().time() + agent.cfp_timeout

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

            if not proposals:
                await asyncio.sleep(2)
                return

            winner = min(proposals, key=lambda x: x[2])
            losers = [p for p in proposals if p != winner]
            await agent.log(f"[CNP] VENCEDOR: {winner[0]} (lead_time={winner[1]}, cost={winner[2]}). Losers={len(losers)}")

            for s, _, _ in losers:
                rej = Message(to=s)
                rej.set_metadata("protocol", "cnp")
                rej.set_metadata("performative", "reject-proposal")
                rej.body = "rejected"
                await self.send(rej)

            acc = Message(to=winner[0])
            acc.set_metadata("protocol", "cnp")
            acc.set_metadata("performative", "accept-proposal")
            acc.body = "accepted"
            await self.send(acc)

            reply = await self.receive(timeout=agent.inform_timeout)
            if reply and reply.metadata.get("performative") == "inform":
                await agent.log(f"[CNP] INFORM do vencedor: {reply.body}")
                agent.env.metrics["cnp_accepts"] += 1
            else:
                await agent.log("[CNP] Timeout à espera de INFORM do vencedor")

            await asyncio.sleep(random.uniform(3, 6))
