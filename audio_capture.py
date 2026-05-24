import sounddevice as sd
import numpy as np
from collections import deque
import threading

SAMPLE_RATE = 16000
CHUNK_SIZE = 512  # silero-VAD 16kHz対応サイズ（256/512/768）


class AudioCapture:
    def __init__(self, device=None):
        self.device = device
        self._queue: deque = deque(maxlen=2000)
        self._lock = threading.Lock()
        self.recording = False
        self._stream = None

    def _callback(self, indata, frames, time_info, status):
        if self.recording:
            chunk = indata[:, 0].astype(np.float32).copy()
            with self._lock:
                self._queue.append(chunk)

    def start(self):
        self.recording = True
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            blocksize=CHUNK_SIZE,
            dtype="float32",
            callback=self._callback,
            device=self.device,
        )
        self._stream.start()

    def stop(self):
        self.recording = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def get_chunk(self) -> np.ndarray | None:
        with self._lock:
            return self._queue.popleft() if self._queue else None

    @staticmethod
    def list_devices():
        return sd.query_devices()
