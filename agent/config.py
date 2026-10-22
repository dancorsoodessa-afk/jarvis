import os
from dataclasses import dataclass


SUPPORTED_PROVIDERS = ("huggingface",)
DEFAULT_CHAT_URL = "https://router.huggingface.co/v1/chat/completions"


def normalize_chat_url(value: str | None) -> str:
    """Force all cloud AI traffic through Hugging Face Inference API."""
    return DEFAULT_CHAT_URL



def normalize_provider(value: str | None) -> str:
    provider = (value or "huggingface").strip().lower()
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
    return "huggingface"


@dataclass
class Settings:
    """Runtime settings for Hugging Face Inference API."""

    provider: str = "huggingface"
    chat_url: str = ""
    chat_key: str = ""
    chat_model: str = "Qwen/Qwen2.5-7B-Instruct"
    fast_model: str = "Qwen/Qwen2.5-7B-Instruct"
    reasoning_model: str = "Qwen/Qwen2.5-7B-Instruct"
    coding_model: str = "Qwen/Qwen2.5-7B-Instruct"
    additional_model: str = "Qwen/Qwen2.5-7B-Instruct"
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
        return self.provider == "local-vulkan"

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
        return cls(
            provider=provider,
            chat_url=normalize_chat_url(os.environ.get("JARVIS_CHAT_URL")),
            chat_key=os.environ.get("JARVIS_CHAT_KEY", "") or os.environ.get("HF_TOKEN", ""),
            chat_model=os.environ.get("JARVIS_CHAT_MODEL", "Qwen/Qwen2.5-7B-Instruct").strip() or "Qwen/Qwen2.5-7B-Instruct",
            fast_model=os.environ.get("JARVIS_FAST_MODEL", os.environ.get("JARVIS_CHAT_MODEL", "Qwen/Qwen2.5-7B-Instruct")).strip() or "Qwen/Qwen2.5-7B-Instruct",
            reasoning_model=os.environ.get("JARVIS_REASONING_MODEL", "Qwen/Qwen2.5-7B-Instruct").strip() or "Qwen/Qwen2.5-7B-Instruct",
            coding_model=os.environ.get("JARVIS_CODING_MODEL", "Qwen/Qwen2.5-7B-Instruct").strip() or "Qwen/Qwen2.5-7B-Instruct",
            additional_model=os.environ.get("JARVIS_ADDITIONAL_MODEL", "Qwen/Qwen2.5-7B-Instruct").strip() or "Qwen/Qwen2.5-7B-Instruct",
            llama_cli=os.environ.get("JARVIS_LLAMA_CLI", "llama-cli").strip(),
            model=os.environ.get("JARVIS_MODEL", "model.gguf").strip(),
            ctx=ctx,
            threads=threads,
            memory_path=os.environ.get("JARVIS_MEMORY", "jarvis_memory.json"),
            kg_path=os.environ.get("JARVIS_KG"),
        )
