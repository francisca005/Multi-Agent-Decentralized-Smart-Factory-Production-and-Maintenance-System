# agents/supervisor_agent.py
import asyncio
from spade.behaviour import CyclicBehaviour
from agents.base_agent import FactoryAgent

class SupervisorAgent(FactoryAgent):
    def __init__(self, jid, password, env=None,
                 supply_refill_every=10, refill_amount=None, supply_agent_ref=None):
        super().__init__(jid, password, env)
        self.supply_refill_every = supply_refill_every
        self.refill_amount = refill_amount or {"flour": 40, "sugar": 20, "butter": 12}
        self.supply_agent_ref = supply_agent_ref

    class Ticker(CyclicBehaviour):
        async def run(self):
            agent = self.agent
            env = agent.env
            env.tick()
            t = env.time


            if agent.supply_agent_ref and t % agent.supply_refill_every == 0:
                for k, v in agent.refill_amount.items():
                    agent.supply_agent_ref.stock[k] += v
                await agent.log(f"[t={t}] Refill fornecedor: +{agent.refill_amount} | stock fornecedor={agent.supply_agent_ref.stock}")

            if t % 5 == 0:
                m = env.metrics
                await agent.log(
                    f"[t={t}] metrics: ok={m['requests_ok']}, refused={m['requests_refused']}, "
                    f"delivered(fl,sg,bt)=({m['delivered_flour']},{m['delivered_sugar']},{m['delivered_butter']}), "
                    f"failures={m['machine_failures']}, repairs_started={m['repairs_started']}, "
                    f"repairs_finished={m['repairs_finished']}, downtime_ticks={m['machine_downtime_ticks']}, "
                    f"cnp_cfp={m['cnp_cfp']}, cnp_accepts={m['cnp_accepts']}"
                )

            await asyncio.sleep(1)

    async def setup(self):
        await self.log(f"iniciado. refill_cada={self.supply_refill_every} ticks | refill={self.refill_amount}")
        self.add_behaviour(self.Ticker())



