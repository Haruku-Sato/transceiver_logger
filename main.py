import tkinter as tk


def run_mode_selector() -> str | None:
    """オンライン/オフラインを選択する起動画面。tkinter以外のimportは一切しない。"""
    result: list[str] = []

    win = tk.Tk()
    win.title("トランシーバ記録システム")
    win.resizable(False, False)
    win.configure(bg="#f0f4f8")

    # 画面中央に配置
    win.update_idletasks()
    w, h = 520, 300
    x = (win.winfo_screenwidth() - w) // 2
    y = (win.winfo_screenheight() - h) // 2
    win.geometry(f"{w}x{h}+{x}+{y}")

    tk.Label(
        win, text="トランシーバ記録システム",
        font=("", 17, "bold"), bg="#f0f4f8", fg="#1a2744"
    ).pack(pady=(36, 4))

    tk.Label(
        win, text="動作モードを選択してください",
        font=("", 10), bg="#f0f4f8", fg="#666"
    ).pack(pady=(0, 28))

    btn_frame = tk.Frame(win, bg="#f0f4f8")
    btn_frame.pack()

    def choose(mode: str):
        result.append(mode)
        win.destroy()

    # ── オンラインカード
    card_online = tk.Frame(btn_frame, bg="#d2e6ff", padx=18, pady=14)
    card_online.pack(side="left", padx=18)
    tk.Button(
        card_online, text="🌐  オンラインモード",
        font=("", 12, "bold"), bg="#d2e6ff", activebackground="#b8d4f8",
        relief="flat", cursor="hand2",
        command=lambda: choose("online")
    ).pack()
    tk.Label(
        card_online,
        text="ブラウザ連携・高速起動\nWhisper / AI はクラウドで処理",
        bg="#d2e6ff", fg="#444", font=("", 9), justify="center"
    ).pack(pady=(6, 0))

    # ── オフラインカード
    card_offline = tk.Frame(btn_frame, bg="#c8f0d8", padx=18, pady=14)
    card_offline.pack(side="left", padx=18)
    tk.Button(
        card_offline, text="💻  オフラインモード",
        font=("", 12, "bold"), bg="#c8f0d8", activebackground="#aee0c0",
        relief="flat", cursor="hand2",
        command=lambda: choose("offline")
    ).pack()
    tk.Label(
        card_offline,
        text="ローカル Whisper・全機能\nインターネット接続不要",
        bg="#c8f0d8", fg="#444", font=("", 9), justify="center"
    ).pack(pady=(6, 0))

    win.protocol("WM_DELETE_WINDOW", win.destroy)
    win.mainloop()

    return result[0] if result else None


if __name__ == "__main__":
    mode = run_mode_selector()
    if not mode:
        exit(0)

    # ── モード確定後に初めて重いモジュールをimportする
    from ui import App

    root = tk.Tk()
    app = App(root, mode=mode)
    root.mainloop()
