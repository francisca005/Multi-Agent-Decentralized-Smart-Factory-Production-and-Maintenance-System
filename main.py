# main.py
import asyncio
from environment import FactoryEnvironment
from agents.supply_cnp_agent import SupplyCNPAgent
from agents.machine_cnp_agent import MachineCNPAgent
from agents.supervisor_agent import SupervisorAgent

DOMAIN = "192.168.68.106"
PWD = "12345"

async def main():
    print("\nFase 4 – Multi-Machine Coordination iniciada.\n")


    env = FactoryEnvironment()

    # === Suppliers ===
    supplierA = SupplyCNPAgent(f"supplierA@{DOMAIN}", PWD, env=env,
                               name="A",
                               stock_init={"flour": 60, "sugar": 40, "butter": 30},
                               capacity={"flour": 50, "sugar": 30, "butter": 20})
    supplierB = SupplyCNPAgent(f"supplierB@{DOMAIN}", PWD, env=env,
                               name="B",
                               stock_init={"flour": 45, "sugar": 50, "butter": 25},
                               capacity={"flour": 50, "sugar": 30, "butter": 20})
    await supplierA.start(auto_register=True)
    await supplierB.start(auto_register=True)

    # === Machines ===
    suppliers = [f"supplierA@{DOMAIN}", f"supplierB@{DOMAIN}"]
    machine1 = MachineCNPAgent(f"machine1@{DOMAIN}", PWD, env=env,
                               suppliers=suppliers,
                               batch={"flour": 10, "sugar": 5, "butter": 3},
                               name="M1")
    machine2 = MachineCNPAgent(f"machine2@{DOMAIN}", PWD, env=env,
                               suppliers=suppliers,
                               batch={"flour": 8, "sugar": 4, "butter": 2},
                               name="M2")
    await machine1.start(auto_register=True)
    await machine2.start(auto_register=True)

    # === Supervisor ===
    supervisor = SupervisorAgent(f"supervisor@{DOMAIN}", PWD, env=env,
                                 supply_refill_every=10,
                                 refill_amount={"flour": 30, "sugar": 20, "butter": 10},
                                 supply_agent_ref=supplierA)
    await supervisor.start(auto_register=True)

    MAX_TICKS = 500
    idle_ticks = 0

    while env.time < MAX_TICKS:
        await env.tick()
        if env.metrics["cnp_cfp"] == env.metrics["cnp_accepts"]:
            idle_ticks += 1
        else:
            idle_ticks = 0
        if idle_ticks >= 10:
            print("Nenhum novo contrato nos últimos 10 ticks. Terminando simulação.")
            break

    await asyncio.sleep(50)
    print("Execução terminada (Fase 4 – Multi-Machine CNP).")

if __name__ == "__main__":
    asyncio.run(main())
