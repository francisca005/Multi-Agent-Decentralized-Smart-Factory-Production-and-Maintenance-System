# agents/machine_cnp_agent.py
# -*- coding: utf-8 -*-
from agents.base_agent import FactoryAgent
from spade.behaviour import CyclicBehaviour
from spade.message import Message
import asyncio
import random

class MachineCNPAgent(FactoryAgent):

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

        # estado
        self.is_failed = False
        self.repair_ticks_remaining = 0
        self.is_machine = True

        # capacidades / pipeline
        self.capabilities = ["cutting", "mixing", "baking", "packaging"]
        self.pipeline_stages = ["cutting", "mixing", "baking", "packaging"]
        self.stage_times = {"cutting": 2, "mixing": 3, "baking": 4, "packaging": 2}

        self.job_queue = []
        self.current_job = None
        self.current_stage_ticks_remaining = 0
        self.last_job_id = 0

    async def setup(self):
        self.env.register_agent(self)
        await self.log(f"(CNP Initiator {self.agent_name}) suppliers={self.suppliers} | batch={self.batch}")
        self.add_behaviour(self.CNPInitiator())

    # -----------------------------------------
    # Jobs
    # -----------------------------------------
    def create_job_after_delivery(self):
        self.last_job_id += 1
        job = {
            "id": self.last_job_id,
            "type": "cookie",                     
            "pipeline": list(self.pipeline_stages),
            "current_stage_idx": 0,
            "batch": self.batch.copy()
        }
        self.job_queue.append(job)
        return job


    async def process_current_job_tick(self):
        job = self.current_job
        stage = job["pipeline"][job["current_stage_idx"]]
        self.current_stage_ticks_remaining -= 1

        await self.log(
            f"[JOB] {self.agent_name} job={job['id']} etapa={stage} "
            f"restam {self.current_stage_ticks_remaining} ticks"
        )

        if self.current_stage_ticks_remaining <= 0:
            if job["current_stage_idx"] < len(job["pipeline"]) - 1:
                job["current_stage_idx"] += 1
                next_stage = job["pipeline"][job["current_stage_idx"]]
                self.current_stage_ticks_remaining = self.stage_times[next_stage]
                await self.log(f"[JOB] Job {job['id']} entrou na etapa {next_stage}")
            else:
                await self.log(f"[JOB] Job {job['id']} concluído!")
                self.env.metrics["jobs_completed"] += 1
                self.current_job = None

        await asyncio.sleep(1)

    async def maybe_start_next_job(self):
        if self.current_job is None and self.job_queue:
            self.current_job = self.job_queue.pop(0)
            stage = self.current_job["pipeline"][0]
            self.current_stage_ticks_remaining = self.stage_times[stage]
            await self.log(f"[JOB] Início do job {self.current_job['id']} etapa={stage}")
            await asyncio.sleep(1)
            return True
        return False
    
    async def try_delegate_current_job(self):
        """
        Tenta passar o job atual para outra máquina compatível.
        Critério:
        - outra máquina is_machine == True
        - não está falhada
        - (idealmente) não está ocupada com current_job
        - tem capability para a etapa atual
        """
        if self.current_job is None:
            return

        job = self.current_job
        stage_idx = job["current_stage_idx"]
        stage = job["pipeline"][stage_idx]

        # Procurar candidata
        for other in self.env.agents:
            if other is self:
                continue
            if not getattr(other, "is_machine", False):
                continue
            if getattr(other, "is_failed", False):
                continue

            # Verifica se tem capacidade para esta etapa
            if stage not in getattr(other, "capabilities", []):
                continue

            # (opcional) só delegar se a outra máquina estiver livre
            if getattr(other, "current_job", None) is not None:
                continue

            # Criar uma cópia do job para a outra máquina
            new_job = {
                "id": job["id"],
                "type": job.get("type", "cookie"),      
                "pipeline": list(job["pipeline"]),
                "current_stage_idx": stage_idx,
                "batch": job["batch"].copy(),
            }


            # Transferir também o tempo restante nesta etapa, se fizer sentido
            if hasattr(self, "current_stage_ticks_remaining"):
                other.current_stage_ticks_remaining = self.current_stage_ticks_remaining
            else:
                # fallback: recalcula tempo para esta etapa
                other.current_stage_ticks_remaining = other.stage_times[stage]

            other.current_job = new_job

            # Limpar o job local
            self.current_job = None
            self.current_stage_ticks_remaining = 0

            # Atualizar métricas e logs
            self.env.metrics["jobs_delegated"] += 1
            await self.log(
                f"[DELEGATE] Job {job['id']} (etapa={stage}) delegado para {other.agent_name}."
            )
            await other.log(
                f"[DELEGATE] Recebi job {job['id']} da máquina {self.agent_name}, retomando etapa {stage}."
            )
            return

        # Se chegou aqui, ninguém pôde assumir o job
        self.env.metrics["jobs_lost"] += 1
        await self.log(
            f"[DELEGATE] Nenhuma máquina disponível para assumir job {job['id']} na etapa {stage}. Job perdido."
        )
        self.current_job = None
        self.current_stage_ticks_remaining = 0


    # -----------------------------------------
    # CNP Behaviour
    # -----------------------------------------
    class CNPInitiator(CyclicBehaviour):
        async def run(self):
            agent = self.agent

            # evitar falhar repetidamente enquanto já está avariada
            if agent.is_failed:
                return

            # 2) Falha aleatória
            if random.random() < agent.failure_rate:
                agent.is_failed = True
                agent.env.metrics["machine_failures"] += 1
                await agent.log(f"[FAILURE] {agent.agent_name} avariou! A tentar delegar job atual...")

                # Tentar delegar o job atual para outra máquina compatível
                await agent.try_delegate_current_job()

                # Notificar manutenção (como antes)
                if agent.maintenance:
                    await agent.maintenance.receive_failure(agent)

                return


            # 3) Pipeline
            if agent.current_job is not None:
                await agent.process_current_job_tick()
                return

            if await agent.maybe_start_next_job():
                return

            # 4) CNP normal
            body = (
                f"ingredients: flour={agent.batch['flour']}, "
                f"sugar={agent.batch['sugar']}, butter={agent.batch['butter']}"
            )

            for supplier in agent.suppliers:
                msg = Message(to=supplier)
                msg.set_metadata("performative", "cfp")
                msg.set_metadata("protocol", "cnp")
                msg.thread = f"cnp-{agent.agent_name}-{agent.env.time}"
                msg.body = body

                await self.send(msg)
                await agent.log(f"[{agent.agent_name}] CFP enviado a {supplier}: {msg.body}")
                await asyncio.sleep(0.1)

            agent.env.metrics["cnp_cfp"] += 1

            proposals = []
            timeout = asyncio.get_event_loop().time() + agent.cfp_timeout

            while asyncio.get_event_loop().time() < timeout:
                reply = await self.receive(timeout=0.5)
                if reply:
                    pf = reply.metadata.get("performative")
                    if pf == "propose":
                        data = reply.body.split(";")
                        lead = int(data[0].split("=")[1])
                        cost = int(data[1].split("=")[1])
                        proposals.append((str(reply.sender), lead, cost))
                        await agent.log(f"[CNP] PROPOSE de {reply.sender}: lead={lead}, cost={cost}")
                    elif pf == "refuse":
                        await agent.log(f"[CNP] REFUSE de {reply.sender}: {reply.body}")

            if not proposals:
                await agent.log("[CNP] Nenhuma proposta. Aguardando refill...")
                await asyncio.sleep(random.uniform(5, 8))
                return

            # vencedor
            winner = min(proposals, key=lambda p: p[2])
            losers = [p for p in proposals if p != winner]

            await agent.log(f"[CNP] VENCEDOR: {winner[0]} cost={winner[2]}")

            for s, _, _ in losers:
                rej = Message(to=s)
                rej.set_metadata("performative", "reject-proposal")
                rej.set_metadata("protocol", "cnp")
                rej.body = "rejected"
                await self.send(rej)

            acc = Message(to=winner[0])
            acc.set_metadata("performative", "accept-proposal")
            acc.set_metadata("protocol", "cnp")
            acc.body = "accepted"
            await self.send(acc)

            reply = await self.receive(timeout=agent.inform_timeout)
            if reply and reply.metadata.get("performative") == "inform":
                await agent.log(f"[CNP] INFORM recebido: {reply.body}")
                agent.env.metrics["cnp_accepts"] += 1

                job = agent.create_job_after_delivery()
                await agent.log(f"[JOB] Criado job {job['id']} após entrega.")
            else:
                await agent.log("[CNP] Timeout à espera de INFORM.")

            await asyncio.sleep(random.uniform(3, 6))




