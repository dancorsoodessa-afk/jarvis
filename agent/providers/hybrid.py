"""Internet-first JARVIS with automatic offline fallback."""

import time


class HybridProvider:
    name = "JARVIS"

    def __init__(self, cloud, local, offline_retry_seconds: int = 20):
        self.cloud = cloud
        self.local = local
        self.offline_retry_seconds = offline_retry_seconds
        self._offline_until = 0.0
        self.tool_executor = None

    @property
    def system_prompt(self):
        return self.cloud.system_prompt

    @system_prompt.setter
    def system_prompt(self, value):
        self.cloud.system_prompt = value
        self.local.system_prompt = value

    @property
    def history(self):
        return self.cloud.history

    def generate(self, prompt, tools=None, max_steps=4) -> str:
        if time.monotonic() >= self._offline_until:
            try:
                self.cloud.tool_executor = self.tool_executor
                answer = self.cloud.generate(prompt, tools=tools, max_steps=max_steps)
                self._offline_until = 0.0
                return answer
            except Exception:
                self._offline_until = time.monotonic() + self.offline_retry_seconds

        self.local.system_prompt = self.cloud.system_prompt
        return self.local.generate(prompt, tools=tools, max_steps=1)
