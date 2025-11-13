# main.py
import asyncio
from environment import FactoryEnvironment
from agents.supply_cnp_agent import SupplyCNPAgent
from agents.machine_cnp_agent import MachineCNPAgent
from agents.supervisor_agent import SupervisorAgent
from agents.maintenance_agent import MaintenanceAgent

DOMAIN = "192.168.1.218"
PWD = "12345"

async def main():
    print("\nMulti-Machine Coordination iniciada.\n")

    # === Environment ===
    env = FactoryEnvironment()

    # === Suppliers ===
    supplierA = SupplyCNPAgent(
        f"supplierA@{DOMAIN}", PWD, env=env,
        name="A",
        stock_init={"flour": 60, "sugar": 40, "butter": 30},
        capacity={"flour": 50, "sugar": 30, "butter": 20}
    )
    supplierB = SupplyCNPAgent(
        f"supplierB@{DOMAIN}", PWD, env=env,
        name="B",
        stock_init={"flour": 45, "sugar": 50, "butter": 25},
        capacity={"flour": 50, "sugar": 30, "butter": 20}
    )
    await supplierA.start(auto_register=True)
    await supplierB.start(auto_register=True)

    # === Maintenance Agent ===
    maintenance = MaintenanceAgent(
        f"maintenance@{DOMAIN}", PWD, env=env
    )
    await maintenance.start(auto_register=True)

    # 🔹 IMPORTANTE: dizer ao ambiente quem é o maintenance agent
    env.set_maintenance_agent(maintenance)

    # === Machines ===
    suppliers = [f"supplierA@{DOMAIN}", f"supplierB@{DOMAIN}"]

    machine1 = MachineCNPAgent(
        f"machine1@{DOMAIN}", PWD, env=env,
        suppliers=suppliers,
        batch={"flour": 10, "sugar": 5, "butter": 3},
        name="M1",
        maintenance=maintenance,
        failure_rate=0.05
    )
    machine2 = MachineCNPAgent(
        f"machine2@{DOMAIN}", PWD, env=env,
        suppliers=suppliers,
        batch={"flour": 8, "sugar": 4, "butter": 2},
        name="M2",
        maintenance=maintenance,
        failure_rate=0.04
    )

    await machine1.start(auto_register=True)
    await machine2.start(auto_register=True)

    # === Supervisor ===
    supervisor = SupervisorAgent(
        f"supervisor@{DOMAIN}", PWD, env=env,
        supply_refill_every=10,
        refill_amount={"flour": 30, "sugar": 20, "butter": 10},
        supply_agent_ref=supplierA
    )
    await supervisor.start(auto_register=True)

    # === Simulation Loop ===
    MAX_TICKS = 500
    idle_ticks = 0

    # lista de máquinas, para verificarmos se há jobs ativos
    machines = [machine1, machine2]

    while env.time < MAX_TICKS:
        # avança o tempo global
        await env.tick()

        # há algum job ainda a ser processado ou em fila?
        active_jobs = any(
            (m.current_job is not None) or (len(m.job_queue) > 0)
            for m in machines
        )

        # critério de "inatividade":
        # - não há CNP pendentes (cnp_cfp == cnp_accepts)
        # - E não há jobs em processamento
        if env.metrics["cnp_cfp"] == env.metrics["cnp_accepts"] and not active_jobs:
            idle_ticks += 1
        else:
            idle_ticks = 0

        if idle_ticks >= 10:
            print("Nenhum novo contrato nem jobs ativos nos últimos 10 ticks. Terminando simulação.")
            break

        await asyncio.sleep(0.1)

    print("Execução terminada (Multi-Machine CNP + Pipeline + Manutenção).")

    # === Mostrar métricas finais (útil para relatório) ===
    print("\n=== MÉTRICAS FINAIS ===")
    for k, v in env.metrics.items():
        print(f"{k}: {v}")

    # === Stop Agents ===
    await machine1.stop()
    await machine2.stop()
    await supplierA.stop()
    await supplierB.stop()
    await maintenance.stop()
    await supervisor.stop()


if __name__ == "__main__":
    asyncio.run(main())
