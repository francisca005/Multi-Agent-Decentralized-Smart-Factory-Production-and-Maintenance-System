# environment.py
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
            # --- CNP metrics ---
            "cnp_cfp": 0,
            "cnp_accepts": 0,
        }

    def tick(self):
        self.time += 1
