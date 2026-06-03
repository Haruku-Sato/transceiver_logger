import json
import os

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

DEFAULT_CONFIG: dict = {
    "provider": "ChatGPT",
    "model": "gpt-4o-mini",
    "api_key": "",
    "azure_endpoint": "",
    "budget_jpy": 100.0,
    "context_window": 10,
    "ai_enabled": False,
    "supabase_url": "",
    "supabase_key": "",
    "supabase_enabled": False,
    "web_mode": False,
}


def load_config() -> dict:
    if not os.path.exists(_CONFIG_PATH):
        return DEFAULT_CONFIG.copy()
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        cfg = DEFAULT_CONFIG.copy()
        cfg.update(data)
        return cfg
    except Exception:
        return DEFAULT_CONFIG.copy()


def save_config(cfg: dict) -> None:
    merged = DEFAULT_CONFIG.copy()
    merged.update(cfg)
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
