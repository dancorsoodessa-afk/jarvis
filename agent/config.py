import os
from dataclasses import dataclass


@dataclass
class Settings:
    """Runtime settings for free/local AI providers only."""

    provider: str = "openai-compatible"
    chat_url: str = "http://127.0.0.1:11434/v1/chat/completions"
    chat_key: str = ""
    chat_model: str = ""
    llama_cli: str = "llama-cli"
    model: str = "model.gguf"
    ctx: int = 2048
    threads: int = 6
    memory_path: str = "jarvis_memory.json"
    kg_path: str | None = None

    @property
    def use_local(self) -> bool:
        """Backward-compatible view for older callers/tests."""
        return self.provider == "local-vulkan"

    @classmethod
    def from_env(cls) -> "Settings":
        provider = os.environ.get("JARVIS_PROVIDER", "openai-compatible").strip().lower()
        if os.environ.get("JARVIS_LOCAL") == "1":
            provider = "local-vulkan"
        return cls(
            provider=provider,
            chat_url=os.environ.get("JARVIS_CHAT_URL", "http://127.0.0.1:11434/v1/chat/completions"),
            chat_key=os.environ.get("JARVIS_CHAT_KEY", ""),
            chat_model=os.environ.get("JARVIS_CHAT_MODEL", ""),
            llama_cli=os.environ.get("JARVIS_LLAMA_CLI", "llama-cli"),
            model=os.environ.get("JARVIS_MODEL", "model.gguf"),
            ctx=int(os.environ.get("JARVIS_CTX", "2048")),
            threads=int(os.environ.get("JARVIS_THREADS", "6")),
            memory_path=os.environ.get("JARVIS_MEMORY", "jarvis_memory.json"),
            kg_path=os.environ.get("JARVIS_KG"),
        )
