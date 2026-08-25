import os
from dataclasses import dataclass


@dataclass
class Settings:
    """Runtime settings. Local inference is opt-in (JARVIS_LOCAL=1);
    cloud is the default provider per the project performance rule."""

    use_local: bool = False
    llama_cli: str = "llama-cli"
    model: str = "model.gguf"
    ctx: int = 2048
    threads: int = 6
    memory_path: str = "jarvis_memory.json"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            use_local=os.environ.get("JARVIS_LOCAL") == "1",
            llama_cli=os.environ.get("JARVIS_LLAMA_CLI", "llama-cli"),
            model=os.environ.get("JARVIS_MODEL", "model.gguf"),
            ctx=int(os.environ.get("JARVIS_CTX", "2048")),
            threads=int(os.environ.get("JARVIS_THREADS", "6")),
            memory_path=os.environ.get("JARVIS_MEMORY", "jarvis_memory.json"),
        )
