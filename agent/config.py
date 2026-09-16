import os
from dataclasses import dataclass


SUPPORTED_PROVIDERS = ("openai-compatible", "local-vulkan", "airllm")


def normalize_provider(value: str | None) -> str:
    provider = (value or "openai-compatible").strip().lower()
    provider = provider.replace("_", "-").replace(" ", "-")
    aliases = {
        "openai": "openai-compatible",
        "openai-compatible-api": "openai-compatible",
        "openai-compatible-client": "openai-compatible",
        "openai-compatible-provider": "openai-compatible",
        "dragon": "openai-compatible",
        "dragon-local": "openai-compatible",
        "dragon-ai": "openai-compatible",
        "local": "local-vulkan",
        "vulkan": "local-vulkan",
        "llama": "local-vulkan",
        "llama-cpp": "local-vulkan",
    }
    return aliases.get(provider, provider)


@dataclass
class Settings:
    """Runtime settings for local/free AI providers."""

    provider: str = "openai-compatible"
    chat_url: str = ""
    chat_key: str = ""
    chat_model: str = ""
    airllm_model: str = ""
    airllm_max_length: int = 2048
    airllm_max_new_tokens: int = 256
    llama_cli: str = "llama-cli"
    model: str = "model.gguf"
    ctx: int = 2048
    threads: int = 6
    memory_path: str = "jarvis_memory.json"
    kg_path: str | None = None

    def __post_init__(self):
        self.provider = normalize_provider(self.provider)

    @property
    def use_local(self) -> bool:
        return self.provider in {"local-vulkan", "airllm"}

    @classmethod
    def from_env(cls) -> "Settings":
        provider = normalize_provider(os.environ.get("JARVIS_PROVIDER"))
        if os.environ.get("JARVIS_LOCAL") == "1":
            provider = "local-vulkan"
        try:
            ctx = max(256, int(os.environ.get("JARVIS_CTX", "2048")))
        except ValueError:
            ctx = 2048
        try:
            threads = max(1, int(os.environ.get("JARVIS_THREADS", "6")))
        except ValueError:
            threads = 6
        try:
            airllm_max_length = max(256, int(os.environ.get("JARVIS_AIRLLM_MAX_LENGTH", "2048")))
        except ValueError:
            airllm_max_length = 2048
        try:
            airllm_max_new_tokens = max(1, int(os.environ.get("JARVIS_AIRLLM_MAX_NEW_TOKENS", "256")))
        except ValueError:
            airllm_max_new_tokens = 256
        return cls(
            provider=provider,
            chat_url=os.environ.get("JARVIS_CHAT_URL", "").strip(),
            chat_key=os.environ.get("JARVIS_CHAT_KEY", ""),
            chat_model=os.environ.get("JARVIS_CHAT_MODEL", "").strip(),
            airllm_model=os.environ.get("JARVIS_AIRLLM_MODEL", "").strip(),
            airllm_max_length=airllm_max_length,
            airllm_max_new_tokens=airllm_max_new_tokens,
            llama_cli=os.environ.get("JARVIS_LLAMA_CLI", "llama-cli").strip(),
            model=os.environ.get("JARVIS_MODEL", "model.gguf").strip(),
            ctx=ctx,
            threads=threads,
            memory_path=os.environ.get("JARVIS_MEMORY", "jarvis_memory.json"),
            kg_path=os.environ.get("JARVIS_KG"),
        )
