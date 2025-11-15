# agents/supply_cnp_agent.py
from agents.base_agent import FactoryAgent
from spade.behaviour import CyclicBehaviour
from spade.message import Message
import random
import ast


class SupplyCNPAgent(FactoryAgent):
    def __init__(self, jid, password, env=None, name="Supplier",
                 stock_init=None, capacity=None):
        super().__init__(jid, password, env)
        self.agent_name = name
        self.stock = stock_init or {"flour": 50, "sugar": 30, "butter": 20}
        self.capacity = capacity or {"flour": 50, "sugar": 30, "butter": 20}

        # Armazena entregas pendentes: thread_id → task_info
        self.pending_transports = {}

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

            # =========================================================
            # 1. ROBOT → INFORM (transport_done)
            # =========================================================
            if pf == "inform" and msg.body == "transport_done":
                thread_id = msg.metadata.get("thread")

                if thread_id not in self.agent.pending_transports:
                    await self.agent.log("[SUPPLY] ERRO: entrega sem referência (thread ausente/desconhecida).")
                    return

                info = self.agent.pending_transports.pop(thread_id)
                machine = info["machine"]
                batch = info["batch"]

                # Enviar INFORM final à máquina
                reply = Message(to=machine)
                reply.set_metadata("performative", "inform")
                reply.set_metadata("protocol", "cnp")
                reply.body = f"delivered_materials: {batch}"
                await self.send(reply)

                await self.agent.log(f"[SUPPLY] Materiais entregues por robot. INFORM enviado para máquina {machine}.")
                self.agent.env.metrics["cnp_accepts"] += 1
                return

            # =========================================================
            # 2. MACHINE → CFP
            # =========================================================
            if pf == "cfp":
                # Se stock insuficiente → refuse
                if any(v < 10 for v in self.agent.stock.values()):
                    refuse = Message(to=str(msg.sender))
                    refuse.set_metadata("protocol", "cnp")
                    refuse.set_metadata("performative", "refuse")
                    refuse.body = "insufficient_stock"
                    await self.send(refuse)
                    await self.agent.log(f"[CNP/{self.agent.agent_name}] REFUSE (insufficient_stock)")
                    return

                lead_time = random.randint(2, 6)
                cost = random.randint(15, 22)

                propose = Message(to=str(msg.sender))
                propose.set_metadata("protocol", "cnp")
                propose.set_metadata("performative", "propose")
                propose.body = f"lead_time={lead_time}; cost={cost}"
                await self.send(propose)

                await self.agent.log(
                    f"[CNP/{self.agent.agent_name}] PROPOSE lead_time={lead_time}, cost={cost}"
                )
                return

            # =========================================================
            # 3. MACHINE → ACCEPT-PROPOSAL (supplier foi escolhido)
            # =========================================================
            if pf == "accept-proposal":
                machine_jid = str(msg.sender)
                await self.agent.log(f"[SUPPLY] Pedido aceite da máquina {machine_jid} → delegar robot")

                # retira stock
                for k in self.agent.stock.keys():
                    self.agent.stock[k] = max(0, self.agent.stock[k] - 10)

                # Criar tarefa de entrega
                thread_id = f"cnp-{self.agent.agent_name}-{random.randint(1000,9999)}"
                task = {
                    "type": "deliver_materials",
                    "from_supplier": self.agent.agent_name,
                    "to_machine": machine_jid,
                    "batch": self.agent.capacity.copy(),
                    "distance": 1,
                    "thread": thread_id
                }

                # Enviar CFP aos robots
                proposals = []

                for robot_jid in self.agent.env.robots:
                    m = Message(to=robot_jid)
                    m.set_metadata("performative", "cfp")
                    m.set_metadata("protocol", "cnp")
                    m.set_metadata("thread", thread_id)
                    m.body = str(task)

                    await self.send(m)
                    await self.agent.log(f"[SUPPLY → ROBOT] CFP enviado a {robot_jid}: {task}")

                # --- recolher propostas ---
                timeout = self.agent.env.time + 3
                while self.agent.env.time < timeout:
                    rep = await self.receive(timeout=0.5)
                    if rep and rep.metadata.get("performative") == "propose":
                        raw = rep.body.strip()
                        cost = int(raw.split("=")[1].split(";")[0])
                        proposals.append((str(rep.sender), cost, raw))

                        await self.agent.log(
                            f"[SUPPLY] PROPOSE robot={rep.sender} cost={cost} raw={raw}"
                        )

                if not proposals:
                    await self.agent.log("[SUPPLY] Nenhum robot respondeu → impossível entregar.")
                    return

                # Escolher robot vencedor
                winner = min(proposals, key=lambda x: x[1])
                winner_jid = winner[0]

                # Guardar no pending_transports
                self.agent.pending_transports[thread_id] = {
                    "machine": machine_jid,
                    "batch": self.agent.capacity.copy()
                }

                # enviar rejects
                for r, _, _ in proposals:
                    if r != winner_jid:
                        rej = Message(to=r)
                        rej.set_metadata("performative", "reject-proposal")
                        rej.set_metadata("protocol", "cnp")
                        rej.set_metadata("thread", thread_id)
                        await self.send(rej)

                # enviar accept a quem ganhou
                acc = Message(to=winner_jid)
                acc.set_metadata("performative", "accept-proposal")
                acc.set_metadata("protocol", "cnp")
                acc.set_metadata("thread", thread_id)
                acc.body = str(task)
                await self.send(acc)

                await self.agent.log(f"[SUPPLY] Robot selecionado: {winner_jid} para fazer entrega.")
                return

            # =========================================================
            # 4. MACHINE → REJECT-PROPOSAL
            # =========================================================
            if pf == "reject-proposal":
                await self.agent.log(f"[CNP/{self.agent.agent_name}] REJECT recebido (ignorado).")
                return



