import os
from dataclasses import dataclass

SUPPORTED_PROVIDERS = ("groq",)
DEFAULT_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-oss-20b"


def normalize_chat_url(_value: str | None) -> str:
    """Use GroqCloud's OpenAI-compatible cloud API."""
    return DEFAULT_CHAT_URL


def normalize_provider(_value: str | None) -> str:
    return "groq"


@dataclass
class Settings:
    """Runtime settings for the cloud-only Groq provider."""

    provider: str = "groq"
    chat_url: str = DEFAULT_CHAT_URL
    chat_key: str = ""
    chat_model: str = DEFAULT_MODEL
    fast_model: str = DEFAULT_MODEL
    reasoning_model: str = DEFAULT_MODEL
    coding_model: str = DEFAULT_MODEL
    additional_model: str = DEFAULT_MODEL
    memory_path: str = "jarvis_memory.json"
    kg_path: str | None = None

    def __post_init__(self) -> None:
        self.provider = normalize_provider(self.provider)
        self.chat_url = DEFAULT_CHAT_URL

    @classmethod
    def from_env(cls) -> "Settings":
        default_model = os.environ.get("JARVIS_CHAT_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
        key = os.environ.get("GROQ_API_KEY", "").strip() or os.environ.get("JARVIS_CHAT_KEY", "").strip()
        return cls(
            provider="groq",
            chat_url=DEFAULT_CHAT_URL,
            chat_key=key,
            chat_model=default_model,
            fast_model=os.environ.get("JARVIS_FAST_MODEL", default_model).strip() or default_model,
            reasoning_model=os.environ.get("JARVIS_REASONING_MODEL", default_model).strip() or default_model,
            coding_model=os.environ.get("JARVIS_CODING_MODEL", default_model).strip() or default_model,
            additional_model=os.environ.get("JARVIS_ADDITIONAL_MODEL", default_model).strip() or default_model,
            memory_path=os.environ.get("JARVIS_MEMORY", "jarvis_memory.json").strip() or "jarvis_memory.json",
            kg_path=os.environ.get("JARVIS_KG"),
        )
