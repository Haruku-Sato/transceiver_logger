import xlwings as xw
from datetime import datetime

_target_path: str | None = None
_last_row: int | None = None  # 直前に書いた行番号（修正用）

HEADERS = ["時刻", "話者", "発言内容", "タグ", "要約"]


def set_target(path: str) -> None:
    global _target_path
    _target_path = path


def get_target() -> str | None:
    return _target_path


def _next_row(ws) -> int:
    if ws.range("A1").value is None:
        return 1
    row = 1
    while ws.range(f"A{row}").value is not None:
        row += 1
    return row


def append_row(speaker: str, text: str, tag: str = "", summary: str = "") -> int:
    """行を追記して、書き込んだ行番号を返す"""
    global _last_row

    if not _target_path:
        raise ValueError("出力先Excelファイルが設定されていません")

    wb = xw.Book(_target_path)
    ws = wb.sheets[0]

    next_row = _next_row(ws)

    if next_row == 1:
        ws.range("A1").value = HEADERS
        next_row = 2

    timestamp = datetime.now().strftime("%H:%M:%S")
    ws.range(f"A{next_row}").value = [timestamp, speaker, text, tag, summary]
    _last_row = next_row
    return next_row


def update_last_row(speaker: str, text: str, tag: str = "", summary: str = "") -> None:
    """直前に書いた行を上書きする（修正用）"""
    if not _target_path:
        raise ValueError("出力先Excelファイルが設定されていません")
    if _last_row is None:
        raise ValueError("修正できる直前の記録がありません")

    wb = xw.Book(_target_path)
    ws = wb.sheets[0]

    # 時刻は書き込み済みのものをそのまま保持
    existing_time = ws.range(f"A{_last_row}").value or datetime.now().strftime("%H:%M:%S")
    ws.range(f"A{_last_row}").value = [existing_time, speaker, text, tag, summary]
