import numpy as np
from scipy.signal import butter, sosfilt
from collections import Counter
import vocab_manager

# large-v3-turbo: デコーダ層32→4の蒸留モデル。精度2〜5%低下で速度約8倍
MODEL = "mlx-community/whisper-large-v3-turbo"

SAMPLE_RATE = 16000

# 無線音声の帯域（300〜3400Hz）に限定するバンドパスフィルタ係数
_BANDPASS_SOS = butter(4, [300, 3400], btype="band", fs=SAMPLE_RATE, output="sos")


def _bandpass(audio: np.ndarray) -> np.ndarray:
    """300〜3400Hzに帯域制限。サブバス・高周波ヒスを除去する。"""
    return sosfilt(_BANDPASS_SOS, audio).astype(np.float32)


def _normalize(audio: np.ndarray) -> np.ndarray:
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak * 0.9
    return audio


# Whisperが無音・ノイズ区間で生成しがちな既知のハルシネーション
_HALLUCINATIONS = [
    "ご視聴ありがとうございました",
    "チャンネル登録",
    "高評価",
    "よろしくお願いします",
    "ありがとうございました",
    "お疲れ様でした",
    "字幕",
]

# セグメントの無音確率がこれ以上なら結果を捨てる
_NO_SPEECH_THRESHOLD = 0.6


def _is_hallucination(text: str) -> bool:
    return any(phrase in text for phrase in _HALLUCINATIONS)


def _is_repetitive(text: str) -> bool:
    """ぺぺぺ… / ベベベ… / ательно… のような繰り返しトークンを検出する"""
    clean = text.replace("、").replace("。", "").replace(" ", "") if False else \
            text.replace("、", "").replace("。", "").replace(" ", "")
    if len(clean) < 8:
        return False
    # 最頻出1文字が40%超 → ぺぺぺ… / ベベベ… 系
    top_count = Counter(clean).most_common(1)[0][1]
    if top_count / len(clean) > 0.4:
        return True
    # 最頻出2文字組が8回超 → ательно… 系
    bigrams = [clean[i:i+2] for i in range(len(clean) - 1)]
    if bigrams and Counter(bigrams).most_common(1)[0][1] > 8:
        return True
    return False


def _has_unexpected_script(text: str) -> bool:
    """キリル文字など日本語・英数字以外のスクリプトが含まれていないか確認する"""
    # Cyrillic: U+0400–U+04FF
    return sum(1 for c in text if "Ѐ" <= c <= "ӿ") > 2


def transcribe(audio: np.ndarray) -> str:
    """float32 numpy配列（16kHz）を受け取り、日本語テキストを返す。
    無音・ハルシネーションと判定した場合は空文字を返す。"""
    import mlx_whisper  # 初回呼び出し時のみロード（起動高速化のため遅延import）
    audio = _bandpass(audio)
    audio = _normalize(audio)
    result = mlx_whisper.transcribe(
        audio,
        path_or_hf_repo=MODEL,
        language="ja",
        initial_prompt=vocab_manager.get_prompt(),
        condition_on_previous_text=False,
    )

    # no_speech_prob が高いセグメントは無音と判定して破棄
    segments = result.get("segments", [])
    if not segments:
        return ""
    avg_no_speech = sum(s.get("no_speech_prob", 0.0) for s in segments) / len(segments)
    if avg_no_speech > _NO_SPEECH_THRESHOLD:
        return ""

    text = result["text"].strip()

    if _is_hallucination(text):
        return ""

    if _is_repetitive(text):
        return ""

    if _has_unexpected_script(text):
        return ""

    return text
