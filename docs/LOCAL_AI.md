# Local AI

Jarvis uses a provider abstraction.

The intended local path is:

Jarvis -> LocalVulkanProvider -> llama.cpp -> Vulkan -> RX 570

Ollama is deliberately not part of the dependency chain.

Initial local settings:
- context: 2048
- CPU threads: 6
- GPU layers: 99 (llama.cpp decides what fits)
- generation cap: 512 tokens

If a model does not fit in 4 GB VRAM, reduce GPU layers or use a smaller GGUF model.
Do not increase memory pressure blindly on a 16 GB system.
