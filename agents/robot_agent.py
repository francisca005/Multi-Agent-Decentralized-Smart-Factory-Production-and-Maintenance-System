# -*- coding: utf-8 -*-

from agents.base_agent import FactoryAgent
from spade.behaviour import CyclicBehaviour
from spade.message import Message

import asyncio
import json
import ast
import random


class RobotAgent(FactoryAgent):
    """
    Agente de transporte (robot/worker).

    - Recebe CFPs dos fornecedores para tarefas de entrega de materiais.
    - Responde com PROPOSE (custo) ou REFUSE (se estiver ocupado).
    - Quando recebe ACCEPT-PROPOSAL, simula o transporte e,
      no fim, envia um INFORM de 'transport_done' de volta ao fornecedor.

    Importante: agora o robot propaga SEMPRE o metadata 'thread'
    (quando existir no pedido), para que o Supplier consiga
    casar a entrega com pending_transports[thread].
    """

    def __init__(
        self,
        jid,
        password,
        env=None,
        name="Robot",
        max_load=100,
        speed=1.0,
    ):
        super().__init__(jid, password, env=env)
        self.agent_name = name
        self.is_robot = True

        self.max_load = max_load
        self.speed = speed

        self.busy = False
        self.current_task = None

    async def setup(self):
        await self.log(f"[ROBOT] {self.agent_name} pronto para receber tarefas.")
        self.add_behaviour(self.TransportManagerBehaviour())

    # ------------------------- Helpers -------------------------

    def _parse_task(self, body_str):
        """Tenta JSON depois dict Python (literal_eval)."""
        try:
            return json.loads(body_str)
        except Exception:
            pass
        try:
            return ast.literal_eval(body_str)
        except Exception:
            return None

    async def build_proposal(self, msg):
        """
        Processa uma CFP e devolve PROPOSE/REFUSE (sem enviar).
        Propaga o metadata 'thread' se existir.
        """
        task = self._parse_task(msg.body)
        if task is None:
            await self.log(f"[ROBOT] {self.agent_name} CFP com body inválido: {msg.body}")
            return None

        # Se já estiver ocupado, recusa
        if self.busy:
            reply = Message(to=str(msg.sender))
            reply.set_metadata("protocol", msg.metadata.get("protocol", "cnp"))
            reply.set_metadata("performative", "refuse")
            # thread (se existir)
            th = msg.metadata.get("thread")
            if th is not None:
                reply.set_metadata("thread", th)
            reply.body = "busy"
            return reply

        # Custo simples
        distance = task.get("distance", 1)
        cost = max(1, distance * random.randint(3, 5))

        reply = Message(to=str(msg.sender))
        reply.set_metadata("protocol", msg.metadata.get("protocol", "cnp"))
        reply.set_metadata("performative", "propose")
        # thread (se existir)
        th = msg.metadata.get("thread")
        if th is not None:
            reply.set_metadata("thread", th)
        reply.body = f"cost={cost};distance={distance}"

        await self.log(
            f"[ROBOT] {self.agent_name} CFP recebido → PROPOSE cost={cost}, distance={distance}"
        )
        return reply

    async def execute_task_and_build_informs(self, msg):
        """
        Após ACCEPT-PROPOSAL: simula transporte e devolve os INFORM(s).
        Garante que o INFORM inclui o mesmo 'thread' do pedido.
        """
        task = self._parse_task(msg.body)
        if task is None:
            await self.log(
                f"[ROBOT] {self.agent_name} ACCEPT-PROPOSAL com body inválido: {msg.body}"
            )
            return []

        self.busy = True
        self.current_task = task

        await self.log(f"[ROBOT] {self.agent_name} ACCEPT recebido → iniciar entrega: {task}")

        # Simula transporte
        distance = task.get("distance", 1)
        travel_time = max(1.0, distance * self.speed)
        await asyncio.sleep(travel_time)

        supplier_jid = str(msg.sender)
        inform = Message(to=supplier_jid)
        inform.set_metadata("protocol", msg.metadata.get("protocol", "cnp"))
        inform.set_metadata("performative", "inform")
        # thread do ACCEPT → vai também no INFORM
        thread_id = msg.metadata.get("thread")
        if thread_id is None:
            # fallback: tenta buscar do body da task
            thread_id = task.get("thread")
        if thread_id is not None:
            inform.set_metadata("thread", str(thread_id))
        inform.body = "transport_done"

        await self.log(
            f"[ROBOT] {self.agent_name} entrega concluída → INFORM 'transport_done' enviado para {supplier_jid}"
        )

        self.busy = False
        self.current_task = None

        return [inform]

    # ------------------------- Behaviour -------------------------

    class TransportManagerBehaviour(CyclicBehaviour):
        async def run(self):
            while True:
                msg = await self.receive(timeout=0.2)
                if not msg:
                    break

                protocol = msg.metadata.get("protocol")
                pf = msg.metadata.get("performative")
                if protocol != "cnp":
                    continue

                if pf == "cfp":
                    reply = await self.agent.build_proposal(msg)
                    if reply is not None:
                        await self.send(reply)

                elif pf == "accept-proposal":
                    await self.agent.log(
                        f"[ROBOT] {self.agent.agent_name} recebeu ACCEPT-PROPOSAL de {msg.sender}"
                    )
                    informs = await self.agent.execute_task_and_build_informs(msg)
                    for inf in informs:
                        await self.send(inf)

                elif pf == "reject-proposal":
                    # Propaga thread no log apenas para consistência
                    await self.agent.log(
                        f"[ROBOT] {self.agent.agent_name} teve proposta rejeitada por {msg.sender}"
                    )

            await asyncio.sleep(0.1)

