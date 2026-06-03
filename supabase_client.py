"""Supabase integration — optional. Falls back silently if not configured."""

from __future__ import annotations
import io
import wave

import numpy as np

_client = None
_enabled: bool = False

SAMPLE_RATE = 16000


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


def _audio_to_wav_bytes(audio: np.ndarray) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


def upload_audio_and_insert_pending(
    session_id: str,
    ts: str,
    speaker: str,
    audio: np.ndarray,
) -> int | None:
    """音声をStorageにアップロードしてpendingレコードを挿入、IDを返す。"""
    if not is_enabled():
        return None
    try:
        wav_bytes = _audio_to_wav_bytes(audio)
        path = f"{session_id}/{ts.replace(':', '')}.wav"
        _client.storage.from_("audio").upload(
            path, wav_bytes, {"content-type": "audio/wav"}
        )
        result = _client.table("utterances").insert({
            "session_id": session_id,
            "ts": ts,
            "speaker": speaker,
            "status": "pending",
            "audio_path": path,
        }).execute()
        return result.data[0]["id"] if result.data else None
    except Exception as e:
        print(f"[supabase] upload error: {e}")
        return None


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
            "status": "done",
        }).execute()
    except Exception:
        pass


def update_utterance_ai(
    session_id: str, ts: str, tag: str, summary: str
) -> None:
    if not is_enabled():
        return
    try:
        _client.table("utterances").update({
            "tag": tag,
            "summary": summary,
        }).eq("session_id", session_id).eq("ts", ts).execute()
    except Exception:
        pass
