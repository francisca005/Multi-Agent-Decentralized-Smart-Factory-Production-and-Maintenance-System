# main.py
import asyncio
from agents.supervisor_agent import SupervisorAgent
from agents.supply_cnp_agent import SupplyCNPAgent
from agents.machine_cnp_agent import MachineCNPAgent

DOMAIN = "10.0.100.203"  # ajusta se necessário
PWD = "1234"

async def main():
    # Dois fornecedores CNP com stocks/custos/lead_times "implícitos"
    supplierA = SupplyCNPAgent(f"supplierA@{DOMAIN}", PWD, name="A",
                               initial_stock={"flour": 60, "sugar": 40, "butter": 30})
    supplierB = SupplyCNPAgent(f"supplierB@{DOMAIN}", PWD, name="B",
                               initial_stock={"flour": 45, "sugar": 50, "butter": 25})

    # Máquina initiator: envia CFP aos dois
    machine = MachineCNPAgent(f"machine@{DOMAIN}", PWD,
                              supplier_jids=[f"supplierA@{DOMAIN}", f"supplierB@{DOMAIN}"],
                              request_batch={"flour": 10, "sugar": 5, "butter": 3},
                              cfp_timeout=3, inform_timeout=10)

    supervisor = SupervisorAgent(f"supervisor@{DOMAIN}", PWD,
                                 supply_refill_every=9999,  # sem refill automático aqui
                                 refill_amount={"flour": 0, "sugar": 0, "butter": 0})
    supervisor.supply_agent_ref = None  # não usamos no CNP

    await supplierA.start(auto_register=True)
    await supplierB.start(auto_register=True)
    await machine.start(auto_register=True)
    await supervisor.start(auto_register=True)

    print("Fase 3 (CNP) a correr: Machine ↔ SupplierA/SupplierB.")

    # corre ~45s para observar várias rondas
    await asyncio.sleep(45)

    await supervisor.stop()
    await machine.stop()
    await supplierB.stop()
    await supplierA.stop()

    print("Execução terminada (CNP).")

if __name__ == "__main__":
    asyncio.run(main())
