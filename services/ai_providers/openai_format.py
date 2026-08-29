import json
from urllib.request import Request, urlopen


class OpenAIRequest:
    def __init__(self, spec, api_key, tool, prompt):
        self.spec = spec
        self.api_key = api_key
        self.tool = tool
        self.prompt = prompt

    @property
    def url(self):
        return f"{self.spec.base_url}/chat/completions"

    def payload(self):
        function = {
            "name": self.tool["name"],
            "description": self.tool["description"],
            "parameters": self.tool["input_schema"],
        }
        return {
            "model": self.spec.model,
            "max_tokens": 4000,
            "tools": [{"type": "function", "function": function}],
            "tool_choice": {
                "type": "function",
                "function": {"name": self.tool["name"]},
            },
            "messages": [{"role": "user", "content": self.prompt}],
        }

    def send(self):
        from . import validate_provider_url

        validate_provider_url(self.spec, self.url)
        request = Request(
            self.url,
            data=json.dumps(self.payload()).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
        try:
            arguments = payload["choices"][0]["message"]["tool_calls"][0][
                "function"
            ]["arguments"]
            tool_input = json.loads(arguments) if isinstance(arguments, str) else arguments
            return tool_input.get("suggestions", [])
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError(
                "Model response did not include a valid categorize_transactions "
                "tool call"
            ) from exc
