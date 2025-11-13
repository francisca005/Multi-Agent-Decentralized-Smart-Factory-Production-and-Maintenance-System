# agents/machine_cnp_agent.py
# -*- coding: utf-8 -*-
from agents.base_agent import FactoryAgent
from spade.behaviour import CyclicBehaviour
from spade.message import Message
import asyncio
import random


class MachineCNPAgent(FactoryAgent):
    """
    Máquina que:
      - faz CNP com fornecedores para obter ingredientes
      - cria jobs após cada entrega
      - processa jobs num pipeline de etapas (cutting, mixing, baking, packaging)
      - pode avariar aleatoriamente (falha interna)
      - pede reparação ao MaintenanceAgent
    (Passo A: ainda sem delegação de jobs entre máquinas)
    """

    def __init__(
        self,
        jid,
        password,
        env=None,
        suppliers=None,
        batch=None,
        cfp_timeout=3,
        inform_timeout=5,
        name="Machine",
        maintenance=None,
        failure_rate=0.05,
        capabilities=None,
    ):
        super().__init__(jid, password, env=env)

        # --- CNP / fornecimento ---
        self.suppliers = suppliers or []
        self.batch = batch or {"flour": 10, "sugar": 5, "butter": 3}
        self.cfp_timeout = cfp_timeout
        self.inform_timeout = inform_timeout
        self.agent_name = name

        # --- manutenção / falhas ---
        self.maintenance = maintenance or (env and getattr(env, "maintenance_agent", None))
        self.failure_rate = failure_rate
        self.is_failed = False
        self.repair_ticks_remaining = 0  # usado pelo Environment
        self.is_machine = True  # usado para identificar máquinas no env

        # --- pipeline de produção ---
        # capacidade vêm do MAIN (ou default para todas)
        self.capabilities = capabilities or ["cutting", "mixing", "baking", "packaging"]

        # full factory pipeline (universal reference)
        full_pipeline = ["cutting", "mixing", "baking", "packaging"]

        # pipeline for this machine = only stages it is capable of doing
        self.pipeline_stages = [stage for stage in full_pipeline if stage in self.capabilities]

        # stage times (only for supported stages)
        default_times = {
            "cutting": 2,
            "mixing": 3,
            "baking": 4,
            "packaging": 2,
        }
        self.stage_times = {stage: default_times[stage] for stage in self.pipeline_stages}

        # estado dos jobs
        self.job_queue = []                 # jobs à espera de começar
        self.current_job = None             # job atualmente em processamento
        self.current_stage_ticks_remaining = 0
        self.last_job_id = 0

    # ------------------------------------------------------------------
    # SPADE setup
    # ------------------------------------------------------------------
    async def setup(self):
        # registar agente no ambiente para permitir métricas & manutenção
        if self.env is not None:
            self.env.register_agent(self)

        await self.log(
            f"(CNP Initiator {self.agent_name}) suppliers={self.suppliers} | batch={self.batch}"
        )

        self.add_behaviour(self.CNPInitiator())

    # ------------------------------------------------------------------
    # Gestão de Jobs / Pipeline
    # ------------------------------------------------------------------
    def create_job_after_delivery(self):
        """
        Cria um novo job de produção após uma entrega bem sucedida.
        O job percorre o pipeline definido em self.pipeline_stages.
        """
        self.last_job_id += 1
        job = {
            "id": self.last_job_id,
            "pipeline": list(self.pipeline_stages),
            "current_stage_idx": 0,
            "batch": self.batch.copy(),
        }
        self.job_queue.append(job)
        return job

    async def process_current_job_tick(self):
        """
        Avança um tick na etapa atual do job.
        Quando a etapa acaba, avança para a próxima.
        Quando a última etapa termina, o job é concluído.
        """
        job = self.current_job
        if job is None:
            return

        stage = job["pipeline"][job["current_stage_idx"]]
        self.current_stage_ticks_remaining -= 1

        await self.log(
            f"[JOB] {self.agent_name} job={job['id']} etapa={stage} "
            f"restam {self.current_stage_ticks_remaining} ticks"
        )

        # terminou a etapa?
        if self.current_stage_ticks_remaining <= 0:
            # ainda há etapas seguintes?
            if job["current_stage_idx"] < len(job["pipeline"]) - 1:
                job["current_stage_idx"] += 1
                next_stage = job["pipeline"][job["current_stage_idx"]]
                self.current_stage_ticks_remaining = self.stage_times[next_stage]
                await self.log(f"[JOB] Job {job['id']} entrou na etapa {next_stage}")
            else:
                # job concluído
                await self.log(f"[JOB] Job {job['id']} concluído!")
                if self.env is not None:
                    self.env.metrics["jobs_completed"] += 1
                self.current_job = None
                self.current_stage_ticks_remaining = 0

        await asyncio.sleep(1)

    async def maybe_start_next_job(self):
        """
        Se não houver job em execução mas existir job em fila,
        começa o próximo job na primeira etapa do pipeline.
        """
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

        Critérios:
        - outra máquina: is_machine == True
        - não está falhada
        - está livre (current_job is None)
        - tem capability para a etapa atual
        """
        if self.current_job is None:
            return

        job = self.current_job
        stage_idx = job["current_stage_idx"]
        stage = job["pipeline"][stage_idx]

        # Procurar outra máquina candidata
        for other in self.env.agents:
            if other is self:
                continue
            if not getattr(other, "is_machine", False):
                continue
            if getattr(other, "is_failed", False):
                continue
            if not other.can_handle(stage):
                continue
            if getattr(other, "current_job", None) is not None:
                continue  # já ocupada

            # pipeline da máquina de destino
            dest_pipeline = other.pipeline_stages

            # etapa atual do job
            current_stage = job["pipeline"][stage_idx]

            # garantir que a etapa atual existe no pipeline do destinatário
            if current_stage not in dest_pipeline:
                # segurança máxima — nunca deveria acontecer por causa de can_handle(),
                # mas deixamos para garantir solidez
                continue

            # índice da etapa atual no pipeline do destinatário
            dest_stage_idx = dest_pipeline.index(current_stage)

            # criar job adaptado ao pipeline da máquina destino
            new_job = {
                "id": job["id"],
                "pipeline": list(dest_pipeline),
                "current_stage_idx": dest_stage_idx,
                "batch": job["batch"].copy(),
            }

            other.current_job = new_job

            # transferir também o tempo restante da etapa
            if getattr(self, "current_stage_ticks_remaining", 0) > 0:
                other.current_stage_ticks_remaining = self.current_stage_ticks_remaining
            else:
                # fallback: tempo normal da etapa nessa máquina
                other.current_stage_ticks_remaining = other.stage_times[stage]

            # limpar o job desta máquina
            self.current_job = None
            self.current_stage_ticks_remaining = 0

            # garantir que não existe cópia deste job na queue
            self.job_queue = [j for j in self.job_queue if j["id"] != job["id"]]

            # métricas e logs
            self.env.metrics["jobs_delegated"] += 1
            await self.log(
                f"[DELEGATE] Job {job['id']} (etapa={stage}) delegado para {other.agent_name}."
            )
            await other.log(
                f"[DELEGATE] Recebi job {job['id']} da máquina {self.agent_name}, retomando etapa {stage}."
            )
            return

        # Se não encontrámos nenhuma máquina candidata: job perdido
        self.env.metrics["jobs_lost"] += 1
        await self.log(
            f"[DELEGATE] Nenhuma máquina disponível para assumir job {job['id']} na etapa {stage}. Job perdido."
        )
        self.current_job = None
        self.current_stage_ticks_remaining = 0

    def can_handle(self, stage):
        return stage in self.capabilities

    # ------------------------------------------------------------------
    # CNP Behaviour
    # ------------------------------------------------------------------
    class CNPInitiator(CyclicBehaviour):
        async def run(self):
            agent = self.agent

            # 0) se a máquina já está falhada, não faz nada neste tick
            if agent.is_failed:
                await asyncio.sleep(1)
                return

            # 1) Falha aleatória
            if random.random() < agent.failure_rate:
                agent.is_failed = True
                agent.env.metrics["machine_failures"] += 1
                await agent.log(f"[FAILURE] {agent.agent_name} avariou! A tentar delegar job atual...")

                # tentar delegar o job atual para outra máquina compatível
                await agent.try_delegate_current_job()

                # notificar manutenção
                if agent.maintenance:
                    await agent.maintenance.receive_failure(agent)

                return


            # 2) Pipeline: se há job atual, avançar um tick
            if agent.current_job is not None:
                await agent.process_current_job_tick()
                return

            # 3) Se não há job em execução, tentar iniciar um da fila
            if await agent.maybe_start_next_job():
                return

            # 4) Se não há jobs para processar, fazer ciclo de CNP normal
            body = (
                f"ingredients: flour={agent.batch['flour']}, "
                f"sugar={agent.batch['sugar']}, butter={agent.batch['butter']}"
            )

            for supplier in agent.suppliers:
                msg = Message(to=supplier)
                msg.set_metadata("performative", "cfp")
                msg.set_metadata("protocol", "cnp")

                if agent.env is not None:
                    msg.thread = f"cnp-{agent.agent_name}-{agent.env.time}"
                else:
                    msg.thread = f"cnp-{agent.agent_name}-{random.randint(0, 9999)}"

                msg.body = body

                await self.send(msg)
                await agent.log(f"[{agent.agent_name}] CFP enviado a {supplier}: {msg.body}")
                await asyncio.sleep(0.1)

            if agent.env is not None:
                agent.env.metrics["cnp_cfp"] += 1

            # recolher propostas
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
                        await agent.log(
                            f"[CNP] PROPOSE de {reply.sender}: lead={lead}, cost={cost}"
                        )
                    elif pf == "refuse":
                        await agent.log(f"[CNP] REFUSE de {reply.sender}: {reply.body}")

            if not proposals:
                await agent.log("[CNP] Nenhuma proposta. Aguardando refill...")
                await asyncio.sleep(random.uniform(5, 8))
                return

            # escolher vencedor (custo mínimo)
            winner = min(proposals, key=lambda p: p[2])
            losers = [p for p in proposals if p != winner]

            await agent.log(f"[CNP] VENCEDOR: {winner[0]} cost={winner[2]}")

            # rejeitar restantes
            for s, _, _ in losers:
                rej = Message(to=s)
                rej.set_metadata("performative", "reject-proposal")
                rej.set_metadata("protocol", "cnp")
                rej.body = "rejected"
                await self.send(rej)

            # aceitar vencedor
            acc = Message(to=winner[0])
            acc.set_metadata("performative", "accept-proposal")
            acc.set_metadata("protocol", "cnp")
            acc.body = "accepted"
            await self.send(acc)

            # esperar INFORM (entrega)
            reply = await self.receive(timeout=agent.inform_timeout)
            if reply and reply.metadata.get("performative") == "inform":
                await agent.log(f"[CNP] INFORM recebido: {reply.body}")
                if agent.env is not None:
                    agent.env.metrics["cnp_accepts"] += 1

                # criar job após a entrega
                job = agent.create_job_after_delivery()
                await agent.log(f"[JOB] Criado job {job['id']} após entrega.")
            else:
                await agent.log("[CNP] Timeout à espera de INFORM.")

            await asyncio.sleep(random.uniform(3, 6))
