class CloudProvider:
    name = "cloud"

    def __init__(self, generate_fn):
        self._generate_fn = generate_fn

    def generate(self, prompt: str) -> str:
        return self._generate_fn(prompt)
