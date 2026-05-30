"""Multi-provider AI client for transcription summarization and tagging."""

import json
import re

PROVIDERS: dict[str, dict] = {
    "ChatGPT": {
        "package": "openai",
        "models": ["gpt-4o-mini", "gpt-4o"],
    },
    "Gemini": {
        "package": "google-generativeai",
        "models": ["gemini-1.5-flash", "gemini-1.5-pro"],
    },
    "Claude": {
        "package": "anthropic",
        "models": ["claude-haiku-4-5-20251001", "claude-sonnet-4-6"],
    },
    "Azure/Copilot": {
        "package": "openai",
        "models": ["gpt-4o-mini", "gpt-4o"],
    },
}

# JPY per 1M tokens (input, output)
_COST_TABLE: dict[str, dict[str, tuple[float, float]]] = {
    "ChatGPT": {
        "gpt-4o-mini": (18.0, 72.0),
        "gpt-4o": (375.0, 1500.0),
    },
    "Gemini": {
        "gemini-1.5-flash": (11.0, 44.0),
        "gemini-1.5-pro": (180.0, 720.0),
    },
    "Claude": {
        "claude-haiku-4-5-20251001": (38.0, 190.0),
        "claude-sonnet-4-6": (450.0, 2250.0),
    },
    "Azure/Copilot": {
        "gpt-4o-mini": (18.0, 72.0),
        "gpt-4o": (375.0, 1500.0),
    },
}

_SYSTEM_PROMPT = (
    "あなたは無線通話ログのAIアシスタントです。\n"
    "ユーザーから直前の発話リストと新しい発話が与えられます。\n"
    "以下の形式でJSONのみを返してください（説明文不要）：\n"
    "{\"summary\": \"1文以内の簡潔な要約\", \"tag\": \"X.Y.Z\"}\n\n"
    "タグのルール：\n"
    "- タグはLaTeXのセクション番号形式（1, 1.1, 1.1.1, 1.2, 2 など）\n"
    "- 前後の発話と話題のつながりがある場合は同じ親タグを持つ番号を割り当てる\n"
    "- 共通の問題から枝分かれした場合は 1.1.1 と 1.1.2 のように分ける\n"
    "- 全く新しい話題なら新しい番号（2, 3 ...）を割り当てる\n"
    "- 最初の発話は 1 から始める\n"
    "- タグは文字列として返す（例: \"1.2.3\"）"
)


def _build_user_message(text: str, context: list[dict]) -> str:
    lines = []
    if context:
        lines.append("【直前の発話リスト】")
        for i, item in enumerate(context, 1):
            tag = item.get("tag", "")
            spk = item.get("speaker", "不明")
            txt = item.get("text", "")
            lines.append(f"{i}. [{tag}] {spk}: {txt}")
    lines.append("\n【新しい発話】")
    lines.append(text)
    return "\n".join(lines)


def _parse_response(raw: str) -> tuple[str, str]:
    """Return (summary, tag) from raw JSON string, with fallback."""
    raw = raw.strip()
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        raw = match.group(0)
    try:
        data = json.loads(raw)
        summary = str(data.get("summary", "")).strip()
        tag = str(data.get("tag", "")).strip()
        return summary, tag
    except Exception:
        return raw[:60], ""


class AIClient:
    def __init__(self, provider: str, api_key: str, model: str, endpoint: str = ""):
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.endpoint = endpoint

    def summarize_and_tag(
        self, text: str, context: list[dict]
    ) -> dict:
        """
        Returns {"summary": str, "tag": str, "input_tokens": int, "output_tokens": int}.
        Raises on API error.
        """
        user_msg = _build_user_message(text, context)

        if self.provider in ("ChatGPT", "Azure/Copilot"):
            return self._call_openai(user_msg)
        elif self.provider == "Gemini":
            return self._call_gemini(user_msg)
        elif self.provider == "Claude":
            return self._call_claude(user_msg)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

    def _call_openai(self, user_msg: str) -> dict:
        from openai import OpenAI
        kwargs: dict = {"api_key": self.api_key, "timeout": 30.0}
        if self.provider == "Azure/Copilot" and self.endpoint:
            kwargs["base_url"] = self.endpoint
        client = OpenAI(**kwargs)
        resp = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or ""
        summary, tag = _parse_response(raw)
        usage = resp.usage
        return {
            "summary": summary,
            "tag": tag,
            "input_tokens": usage.prompt_tokens if usage else 0,
            "output_tokens": usage.completion_tokens if usage else 0,
        }

    def _call_gemini(self, user_msg: str) -> dict:
        import google.generativeai as genai
        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel(
            model_name=self.model,
            system_instruction=_SYSTEM_PROMPT,
            generation_config={"temperature": 0.2},
        )
        full_prompt = user_msg + "\n\nJSON形式のみで返答してください。"
        resp = model.generate_content(
            full_prompt,
            request_options={"timeout": 30},
        )
        raw = resp.text or ""
        summary, tag = _parse_response(raw)
        usage = resp.usage_metadata
        return {
            "summary": summary,
            "tag": tag,
            "input_tokens": getattr(usage, "prompt_token_count", 0),
            "output_tokens": getattr(usage, "candidates_token_count", 0),
        }

    def _call_claude(self, user_msg: str) -> dict:
        import anthropic
        client = anthropic.Anthropic(api_key=self.api_key, timeout=30.0)
        resp = client.messages.create(
            model=self.model,
            max_tokens=256,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = resp.content[0].text if resp.content else ""
        summary, tag = _parse_response(raw)
        usage = resp.usage
        return {
            "summary": summary,
            "tag": tag,
            "input_tokens": usage.input_tokens if usage else 0,
            "output_tokens": usage.output_tokens if usage else 0,
        }

    def estimate_cost_jpy(self, input_tokens: int, output_tokens: int) -> float:
        rates = _COST_TABLE.get(self.provider, {}).get(self.model)
        if not rates:
            return 0.0
        in_rate, out_rate = rates
        return (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000

    def test_connection(self) -> tuple[bool, str]:
        """Returns (success, message)."""
        try:
            result = self.summarize_and_tag(
                "テスト発話です", []
            )
            return True, f"接続成功（要約: {result['summary']}）"
        except ImportError as e:
            pkg = str(e).split("'")
            pkg_name = pkg[1] if len(pkg) > 1 else str(e)
            return False, f"パッケージ未インストール: {pkg_name}"
        except Exception as e:
            return False, f"エラー: {e}"
