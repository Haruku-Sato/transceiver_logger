from pathlib import Path

VOCAB_PATH = Path("vocab.txt")

DEFAULT_VOCAB = [
    "テント", "搬入", "搬出", "設営", "撤収", "スタッフ", "来場者",
    "トランシーバ", "了解", "確認", "準備完了", "どうぞ", "以上",
    "ステージ", "正門", "裏口", "本部", "教室", "体育館",
]

_vocab: list[str] | None = None


def load_vocab() -> list[str]:
    global _vocab
    if VOCAB_PATH.exists():
        words = [w.strip() for w in VOCAB_PATH.read_text(encoding="utf-8").splitlines() if w.strip()]
        _vocab = words if words else DEFAULT_VOCAB.copy()
    else:
        _vocab = DEFAULT_VOCAB.copy()
    return _vocab.copy()


def save_vocab(words: list[str]) -> None:
    global _vocab
    _vocab = words.copy()
    VOCAB_PATH.write_text("\n".join(words), encoding="utf-8")


def get_prompt() -> str:
    global _vocab
    if _vocab is None:
        load_vocab()
    return "、".join(_vocab)
