from anthropic import Anthropic


class AnthropicRequest:
    def __init__(self, spec, api_key, tool, prompt):
        self.spec = spec
        self.client = Anthropic(api_key=api_key, base_url=spec.base_url)
        self.tool = tool
        self.prompt = prompt

    def send(self):
        from . import validate_provider_url

        validate_provider_url(self.spec, str(self.client.base_url))
        response = self.client.messages.create(
            model=self.spec.model,
            max_tokens=4000,
            tools=[self.tool],
            tool_choice={"type": "tool", "name": "categorize_transactions"},
            messages=[{"role": "user", "content": self.prompt}]
        )
        tool_use = next(
            (block for block in response.content if block.type == "tool_use"),
            None,
        )
        if tool_use is None:
            raise ValueError(
                "Model response did not include a categorize_transactions tool call"
            )
        return tool_use.input.get("suggestions", [])
