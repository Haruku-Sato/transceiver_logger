import numpy as np
from resemblyzer import VoiceEncoder, preprocess_wav
import db_manager

SIMILARITY_THRESHOLD = 0.75
SAMPLE_RATE = 16000

_encoder: VoiceEncoder | None = None


def get_encoder() -> VoiceEncoder:
    global _encoder
    if _encoder is None:
        _encoder = VoiceEncoder()
    return _encoder


def get_embedding(audio: np.ndarray) -> np.ndarray:
    """float32 numpy配列（16kHz）からd-vectorを生成する"""
    enc = get_encoder()
    wav = preprocess_wav(audio, source_sr=SAMPLE_RATE)
    return enc.embed_utterance(wav)


def identify(audio: np.ndarray) -> tuple[str, float]:
    """
    話者を識別して (名前, コサイン類似度) を返す。
    DBが空、または閾値未満の場合は ("不明", similarity) を返す。
    """
    db = db_manager.load_db()
    if not db:
        return "不明", 0.0

    embedding = get_embedding(audio)

    best_name = "不明"
    best_sim = 0.0
    for name, ref in db.items():
        sim = float(np.dot(embedding, ref))  # どちらもL2正規化済み
        if sim > best_sim:
            best_sim = sim
            best_name = name

    if best_sim < SIMILARITY_THRESHOLD:
        return "不明", best_sim

    return best_name, best_sim
