from pathlib import Path
import subprocess

class LocalVulkanProvider:
    """Thin adapter around llama.cpp's llama-cli with Vulkan backend.

    Jarvis does not depend on Ollama. The executable and GGUF model are configurable.
    """

    name = "local-vulkan"

    def __init__(self, llama_cli: str, model: str, ctx: int = 2048, threads: int = 6):
        self.llama_cli = str(Path(llama_cli))
        self.model = str(Path(model))
        self.ctx = ctx
        self.threads = threads

    def generate(self, prompt: str) -> str:
        cmd = [
            self.llama_cli,
            "-m", self.model,
            "-c", str(self.ctx),
            "-t", str(self.threads),
            "-ngl", "99",
            "-n", "512",
            "-p", prompt,
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "llama.cpp failed")
        return result.stdout.strip()
