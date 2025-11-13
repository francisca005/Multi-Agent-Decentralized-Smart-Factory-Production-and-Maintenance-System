# agents/base_agent.py
from spade.agent import Agent
import datetime

class FactoryAgent(Agent):
    def __init__(self, jid, password, env=None):
        super().__init__(jid, password)
        self.env = env

    async def log(self, msg: str):
        """Log message with timestamp and agent name."""
        now = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{self.name}] {msg}")

