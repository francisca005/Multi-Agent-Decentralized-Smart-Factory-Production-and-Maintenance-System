# agents/base_agent.py
from spade.agent import Agent
from spade.message import Message
from environment import env

class FactoryAgent(Agent):
    """
    Base comum: logging, criação de mensagens e acesso ao ambiente partilhado.
    """
    def __init__(self, jid, password):
        super().__init__(jid, password)
        self.log_prefix = self.__class__.__name__
        self.env = env  # referência ao ambiente partilhado (mesmo processo)

    async def log(self, message: str):
        print(f"[{self.log_prefix}] {message}")

    def create_message(self, to_jid: str, body: str, protocol: str = None, performative: str = None):
        msg = Message(to=to_jid)
        msg.body = body
        if protocol:
            msg.set_metadata("protocol", protocol)
        if performative:
            msg.set_metadata("performative", performative)
        return msg

    async def setup(self):
        await self.log("iniciado.")
