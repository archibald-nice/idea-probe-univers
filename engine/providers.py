"""LLM Provider 抽象：DeepSeek 先行（已拍板），可切换 Kimi；本地 Ling 预留位。

均为 OpenAI 兼容 chat/completions 协议，纯 urllib 实现，无第三方依赖。
"""
import json
import os
import urllib.request


class LLMError(RuntimeError):
    pass


class _OpenAICompatProvider(object):
    name = "base"

    def __init__(self, api_key=None, base_url="", model=""):
        self.api_key = api_key or ""
        self.base_url = base_url
        self.model = model

    def chat(self, system, user, temperature=0.4, json_mode=True,
             timeout=120):
        if not self.api_key:
            raise LLMError(
                "{}: API key 未配置（请在仓库根 .env 中填写）".format(self.name))
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        req = urllib.request.Request(
            self.base_url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer {}".format(self.api_key),
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise LLMError("{}: 响应格式异常: {}".format(self.name, data))


class DeepSeek(_OpenAICompatProvider):
    name = "deepseek"

    def __init__(self, api_key=None):
        super().__init__(
            api_key=api_key or os.environ.get("DEEPSEEK_API_KEY"),
            base_url=os.environ.get(
                "DEEPSEEK_BASE_URL", "https://api.deepseek.com/chat/completions"),
            model=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
        )


class Kimi(_OpenAICompatProvider):
    name = "kimi"

    def __init__(self, api_key=None):
        super().__init__(
            api_key=api_key or os.environ.get("KIMI_API_KEY"),
            base_url=os.environ.get(
                "KIMI_BASE_URL", "https://api.moonshot.cn/v1/chat/completions"),
            model=os.environ.get("KIMI_MODEL", "kimi-k2-0711-preview"),
        )


def get_provider():
    """按 .env 的 LLM_PROVIDER 选择 provider，默认 deepseek。"""
    which = os.environ.get("LLM_PROVIDER", "deepseek").strip().lower()
    if which == "deepseek":
        return DeepSeek()
    if which == "kimi":
        return Kimi()
    raise LLMError("未知 LLM_PROVIDER: {}（支持 deepseek / kimi）".format(which))
