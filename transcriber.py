import mlx_whisper
import numpy as np

MODEL = "mlx-community/whisper-large-v3-mlx"

# 文化祭・トランシーバ運用でよく出る語彙を与えて誤変換を抑制する
INITIAL_PROMPT = (
    "テント、搬入、搬出、設営、撤収、スタッフ、来場者、"
    "トランシーバ、了解、確認、準備完了、どうぞ、以上、"
    "ステージ、正門、裏口、本部、教室、体育館"
)


def _normalize(audio: np.ndarray) -> np.ndarray:
    """ピーク正規化：音量のばらつきを補正する"""
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak * 0.9
    return audio


def transcribe(audio: np.ndarray) -> str:
    """float32 numpy配列（16kHz）を受け取り、日本語テキストを返す"""
    audio = _normalize(audio)
    result = mlx_whisper.transcribe(
        audio,
        path_or_hf_repo=MODEL,
        language="ja",
        initial_prompt=INITIAL_PROMPT,
        condition_on_previous_text=False,
    )
    return result["text"].strip()
