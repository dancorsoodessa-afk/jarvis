/// Default AI routing for the standalone Android client.
///
/// Keep these defaults aligned with the documented Hugging Face Inference API
/// contract. Users may change model IDs, but the default endpoint is stable.
const String jarvisDefaultAiEndpoint = 'https://router.huggingface.co/v1';
const String jarvisDefaultModel1 = 'Qwen/Qwen2.5-7B-Instruct-1M';
const String jarvisDefaultModel2 = 'openai/gpt-oss-120b';
const String jarvisDefaultModel3 = 'meta-llama/Llama-3.3-70B-Instruct';
