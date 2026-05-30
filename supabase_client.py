"""Supabase integration — optional. Falls back silently if not configured."""

from __future__ import annotations

_client = None
_enabled: bool = False


def init(url: str, key: str) -> None:
    global _client, _enabled
    if url and key:
        from supabase import create_client
        _client = create_client(url, key)
        _enabled = True
    else:
        _client = None
        _enabled = False


def is_enabled() -> bool:
    return _enabled and _client is not None


def insert_utterance(
    session_id: str,
    ts: str,
    speaker: str,
    text: str,
    tag: str = "",
    summary: str = "",
) -> None:
    if not is_enabled():
        return
    try:
        _client.table("utterances").insert({
            "session_id": session_id,
            "ts": ts,
            "speaker": speaker,
            "text": text,
            "tag": tag,
            "summary": summary,
        }).execute()
    except Exception:
        pass  # Supabase障害時もアプリは継続


def update_utterance_ai(
    session_id: str, ts: str, tag: str, summary: str
) -> None:
    """AI処理後にtag/summaryを後から更新する（バッチ処理用）。"""
    if not is_enabled():
        return
    try:
        _client.table("utterances").update({
            "tag": tag,
            "summary": summary,
        }).eq("session_id", session_id).eq("ts", ts).execute()
    except Exception:
        pass
