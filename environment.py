# environment.py
class Environment:
    def __init__(self):
        self.time = 0
        self.events = []
        self.metrics = {
            # fase 2
            "requests_ok": 0,
            "requests_refused": 0,
            "delivered_flour": 0,
            "delivered_sugar": 0,
            "delivered_butter": 0,
            "machine_failures": 0,
            "repairs_started": 0,
            "repairs_finished": 0,
            "machine_downtime_ticks": 0,
            # fase 3 (CNP)
            "cnp_cfp": 0,
            "cnp_proposals": 0,
            "cnp_accepts": 0,
            "cnp_rejects": 0,
            "cnp_wins_supplier_a": 0,
            "cnp_wins_supplier_b": 0,
        }

    def tick(self):
        self.time += 1

env = Environment()

