import numpy as np
import torch

SAMPLE_RATE = 16000
MIN_SPEECH_SAMPLES = 8000   # 0.5秒未満は無視


# ─────────────────────────────────────────────
# PTT検出器（有線接続用）
# ─────────────────────────────────────────────

class PTTDetector:
    """
    有線接続のイヤホンジャックから来る信号エネルギーでPTT押下を判定する。
    PTT押下中は無線機からのノイズ/音声が常に乗るため、RMSが閾値を超え続ける。
    閾値を下回ったチャンクが release_chunks 個続いたらPTT解放 = 1通話終了とみなす。
    """

    def __init__(self, energy_threshold: float = 0.002, release_chunks: int = 10):
        self.energy_threshold = energy_threshold
        # release_chunks: 512サンプル × 10 ≈ 320ms の無信号でPTT解放
        self.release_chunks = release_chunks
        self._buffer: list[np.ndarray] = []
        self._ptt_active = False
        self._silent_count = 0

    def process(self, chunk: np.ndarray) -> tuple[np.ndarray | None, float]:
        """
        Returns: (完了した音声セグメント or None, 現在のRMSレベル)
        """
        rms = float(np.sqrt(np.mean(chunk ** 2)))

        if rms > self.energy_threshold:
            self._ptt_active = True
            self._silent_count = 0
            self._buffer.append(chunk)
        elif self._ptt_active:
            self._buffer.append(chunk)
            self._silent_count += 1
            if self._silent_count >= self.release_chunks:
                audio = np.concatenate(self._buffer)
                self._buffer = []
                self._silent_count = 0
                self._ptt_active = False
                if len(audio) >= MIN_SPEECH_SAMPLES:
                    return audio, rms
        return None, rms

    @property
    def is_ptt_active(self) -> bool:
        return self._ptt_active

    def reset(self):
        self._buffer = []
        self._silent_count = 0
        self._ptt_active = False


# ─────────────────────────────────────────────
# VAD（マイク/デバッグ用）
# ─────────────────────────────────────────────

MIN_SILENCE_CHUNKS = 15     # ~480ms の無音で発言終了


def _load_silero():
    try:
        from silero_vad import load_silero_vad
        return load_silero_vad()
    except ImportError:
        model, _ = torch.hub.load(
            "snakers4/silero-vad", "silero_vad", force_reload=False
        )
        return model


class VAD:
    def __init__(self, threshold: float = 0.5):
        self._model = _load_silero()
        self.threshold = threshold
        self._buffer: list[np.ndarray] = []
        self._silence_count = 0
        self._in_speech = False

    def process(self, chunk: np.ndarray) -> tuple[np.ndarray | None, float]:
        """
        Returns: (完了した音声セグメント or None, 音声確率)
        PTTDetectorと同じ戻り値形式にする。
        """
        tensor = torch.from_numpy(chunk).float()
        with torch.no_grad():
            result = self._model(tensor, SAMPLE_RATE)
            prob = result.item() if hasattr(result, "item") else float(result)

        if prob >= self.threshold:
            self._in_speech = True
            self._silence_count = 0
            self._buffer.append(chunk)
        elif self._in_speech:
            self._buffer.append(chunk)
            self._silence_count += 1
            if self._silence_count >= MIN_SILENCE_CHUNKS:
                audio = np.concatenate(self._buffer)
                self._buffer = []
                self._silence_count = 0
                self._in_speech = False
                if len(audio) >= MIN_SPEECH_SAMPLES:
                    return audio, prob
        return None, prob

    @property
    def is_ptt_active(self) -> bool:
        return self._in_speech

    def reset(self):
        self._buffer = []
        self._silence_count = 0
        self._in_speech = False
