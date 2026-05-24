import numpy as np
from pathlib import Path

DB_PATH = Path("voiceprint.npz")


def load_db() -> dict:
    if DB_PATH.exists():
        data = np.load(DB_PATH)
        return {k: data[k] for k in data.files}
    return {}


def save_db(db: dict) -> None:
    np.savez(DB_PATH, **db)


def add_speaker(name: str, embeddings: list) -> None:
    """複数のembeddingを平均して1スピーカー分として保存する"""
    db = load_db()
    mean_embed = np.mean(embeddings, axis=0)
    norm = np.linalg.norm(mean_embed)
    if norm > 0:
        mean_embed = mean_embed / norm
    db[name] = mean_embed.astype(np.float32)
    save_db(db)


def get_speakers() -> list:
    return list(load_db().keys())


def delete_speaker(name: str) -> None:
    db = load_db()
    if name in db:
        del db[name]
        save_db(db)
