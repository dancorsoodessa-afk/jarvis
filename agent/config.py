import os
from dataclasses import dataclass


@dataclass
class Settings:
    """Runtime settings for local Core and OpenAI-compatible cloud roles."""

    provider: str = "openai-compatible"
    chat_url: str = "http://127.0.0.1:11434/v1/chat/completions"
    chat_key: str = ""
    chat_model: str = ""
    primary_model: str = "openai/gpt-5.6-luna"
    code_model: str = "z-ai/glm-5.3-flash:free"
    fast_model: str = "deepseek/deepseek-v4-flash:free"
    universal_model_1: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    universal_model_2: str = "nvidia/nemotron-3-super-120b-a12b:free"
    router_enabled: bool = True
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
            primary_model=os.environ.get("JARVIS_PRIMARY_MODEL", "openai/gpt-5.6-luna"),
            code_model=os.environ.get("JARVIS_CODE_MODEL", "z-ai/glm-5.3-flash:free"),
            fast_model=os.environ.get("JARVIS_FAST_MODEL", "deepseek/deepseek-v4-flash:free"),
            universal_model_1=os.environ.get("JARVIS_UNIVERSAL_MODEL_1", "nvidia/nemotron-3-ultra-550b-a55b:free"),
            universal_model_2=os.environ.get("JARVIS_UNIVERSAL_MODEL_2", "nvidia/nemotron-3-super-120b-a12b:free"),
            router_enabled=os.environ.get("JARVIS_ROUTER", "1").strip().lower() not in ("0", "false", "off"),
            llama_cli=os.environ.get("JARVIS_LLAMA_CLI", "llama-cli"),
            model=os.environ.get("JARVIS_MODEL", "model.gguf"),
            ctx=int(os.environ.get("JARVIS_CTX", "2048")),
            threads=int(os.environ.get("JARVIS_THREADS", "6")),
            memory_path=os.environ.get("JARVIS_MEMORY", "jarvis_memory.json"),
            kg_path=os.environ.get("JARVIS_KG"),
        )
