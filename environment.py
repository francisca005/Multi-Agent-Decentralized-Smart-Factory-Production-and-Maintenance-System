# environment.py
# -*- coding: utf-8 -*-
import asyncio
import random

class FactoryEnvironment:

    def __init__(self):
        self.time = 0
        self.metrics = {
            "requests_ok": 0,
            "requests_refused": 0,
            "delivered_flour": 0,
            "delivered_sugar": 0,
            "delivered_butter": 0,
            "machine_failures": 0,
            "repairs_started": 0,
            "repairs_finished": 0,
            "machine_downtime_ticks": 0,
            "cnp_cfp": 0,
            "cnp_accepts": 0,
            "jobs_completed": 0,
            "jobs_delegated": 0,
            "jobs_lost": 0,
        }

        self.agents = []
        self.maintenance_agent = None
        self.external_failure_rate = 0.0
        self.global_job_id = 0

    def register_agent(self, agent):
        self.agents.append(agent)

    def set_maintenance_agent(self, agent):
        self.maintenance_agent = agent

    def get_new_job_id(self):
        self.global_job_id += 1
        return self.global_job_id


    async def tick(self):
        """Avança 1 tick no tempo e processa reparações."""
        self.time += 1

        for m in self.agents:

            # 🔥 IGNORAR agentes que não são máquinas
            if not getattr(m, "is_machine", False):
                continue

            # downtime se falhada
            if getattr(m, "is_failed", False):
                self.metrics["machine_downtime_ticks"] += 1

            # Processar reparação
            if getattr(m, "repair_ticks_remaining", 0) > 0:
                m.repair_ticks_remaining -= 1

                if m.repair_ticks_remaining == 0:
                    # Reparação concluída
                    m.is_failed = False
                    await m.log(
                        f"[MAINTENANCE] Reparação concluída — {m.agent_name} operacional."
                    )
                    self.metrics["repairs_finished"] += 1

            # Falhas externas opcionais
            if (
                self.external_failure_rate > 0
                and not m.is_failed
                and random.random() < self.external_failure_rate
            ):
                m.is_failed = True
                self.metrics["machine_failures"] += 1

                await m.log(
                    f"[FAILURE] {m.agent_name} falhou (detetado pelo ambiente)."
                )

                # delegação opcional
                if hasattr(m, "try_delegate_current_job"):
                    await m.try_delegate_current_job()

                # notificar manutenção
                if self.maintenance_agent:
                    await self.maintenance_agent.receive_failure(m)

        await asyncio.sleep(0.1)
