# トランシーバ記録システム

トランシーバ（無線機）の音声をリアルタイムで文字起こしし、話者を自動識別してExcelに記録するデスクトップアプリです。AIによる要約・タグ付けや、Supabaseを通じたブラウザからのリアルタイム閲覧にも対応しています。

> **Webビューア** は別リポジトリ [transceiver_logger_online](https://github.com/Haruku-Sato/transceiver_logger_online) で管理しています。

---

## 機能一覧

| 機能 | 説明 |
|---|---|
| 自動文字起こし | mlx-whisper（large-v3-turbo）による日本語音声認識 |
| 話者識別 | Resemblyzerの声紋照合（コサイン類似度） |
| PTT / VAD検出 | 有線接続PTT信号またはSilero VADで発言区間を検出 |
| AI要約・タグ付け | BYOK方式でChatGPT / Gemini / Claude / Azureを呼び出し、発言を1文要約してLaTeXセクション番号形式のタグを自動付与 |
| クレジット管理 | API使用コストを円換算して円グラフ表示。残り10%以下で警告 |
| Excelへの自動書き込み | 時刻・話者・発言内容・タグ・要約を既存ファイルに追記 |
| 内蔵Excelビューア | アプリ右ペインでExcelの内容をリアルタイム表示。Ctrl+Cでそのまま貼り付け可 |
| クラウド同期 | Supabaseに発話ログを送信。チームメンバーがブラウザからリアルタイムに閲覧可能 |
| 語彙設定 | Whisperに渡すドメイン語彙を管理してERNOで誤変換を抑制 |

---

## 動作環境

- **macOS**（Apple Silicon推奨 — mlx-whisperがNeural Engineを使用）
- Python 3.10以上

> Intel MacではWhisperのみ `openai-whisper` への差し替えが必要です。

---

## セットアップ

### 1. 依存ライブラリのインストール

```bash
pip install -r requirements.txt
```

**requirements.txt**
```
torch
mlx-whisper
sounddevice
resemblyzer
numpy
xlwings
openpyxl
silero-vad
tksheet
openai
anthropic
google-generativeai
supabase
```

### 2. 起動

```bash
python main.py
```

---

## 使い方

### 声紋DBの作成（DB作成タブ）

登録する人数分、以下を繰り返します。

1. 「名前」欄に話者名を入力
2. 「録音開始」→ トランシーバで発言 → 「録音停止」
3. 複数サンプルを録音して精度を向上（任意）
4. 「DBに保存」で `voiceprint.npz` に書き込み

### 交信の記録（記録・出力タブ）

1. 「出力先」でExcelファイル（.xlsx）を選択・シートを指定
2. 検出方式を選択
   - **PTT信号（有線接続）** — トランシーバのジャックをPCに有線接続する場合
   - **VAD（マイク/デバッグ）** — PCマイクで集音する場合
3. 「記録開始」をクリック
4. 発言を検出するたびに文字起こし・話者識別・Excel書き込みが自動で行われる
5. 誤認識は「直前の記録」欄で編集して「直前を修正・再出力」

### AI要約・タグ付け（AI設定タブ）

1. 使用するAIプロバイダーとモデルを選択
2. APIキーを入力（BYOK — 自分のAPIキーを使用）
3. 予算上限（円）とコンテキスト件数を設定
4. 「設定を保存」→「接続テスト」で動作確認
5. 「AI要約・タグ付けを有効にする」にチェックを入れる

**対応プロバイダー**

| プロバイダー | モデル例 | APIキー取得先 |
|---|---|---|
| ChatGPT | gpt-4o-mini, gpt-4o | platform.openai.com |
| Gemini | gemini-1.5-flash（**無料枠あり**）, gemini-1.5-pro | aistudio.google.com |
| Claude | claude-haiku-4-5, claude-sonnet-4-6 | console.anthropic.com |
| Azure / Copilot | gpt-4o-mini, gpt-4o | portal.azure.com |

**タグ形式** — LaTeXのセクション番号形式（`1`, `1.1`, `1.1.2` など）。AIが前後の発話文脈を見て話題の階層を自動判断します。

### クラウド同期（クラウド設定タブ）

チームメンバーがブラウザからリアルタイムにログを閲覧できます。

#### Supabaseのセットアップ

1. [supabase.com](https://supabase.com) でプロジェクトを作成
2. SQL Editorで以下を実行：

```sql
create table public.utterances (
  id bigserial primary key,
  session_id text not null,
  created_at timestamptz default now(),
  ts text, speaker text, text text,
  tag text, summary text
);
alter table public.utterances enable row level security;
create policy "read"   on public.utterances for select using (true);
create policy "insert" on public.utterances for insert with check (true);
```

3. Settings → API から **Project URL** と **Service Role Key** をコピー
4. アプリの「クラウド設定」タブに貼り付けて保存

#### Webビューアのデプロイ

[transceiver_logger_online](https://github.com/Haruku-Sato/transceiver_logger_online) をVercelにデプロイし、環境変数を設定します。

| 環境変数 | 値 |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | SupabaseのProject URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabaseの `anon public` キー |

---

## Excelの出力形式

| 時刻 | 話者 | 発言内容 | タグ | 要約 |
|---|---|---|---|---|
| 10:32:15 | 山田 | 正門の搬入完了しました。どうぞ | 1.1 | 正門搬入が完了した旨の報告 |
| 10:32:40 | 佐藤 | 了解です。本部も準備できてます | 1.2 | 本部の準備完了を確認 |

---

## ファイル構成

```
transceiver_logger/
├── main.py             # エントリーポイント
├── ui.py               # GUIアプリ本体（Tkinter）
├── audio_capture.py    # 音声入力ストリーム管理
├── vad.py              # PTT検出器 / Silero VAD
├── transcriber.py      # mlx-whisperによる文字起こし
├── speaker_id.py       # Resemblyzerによる話者識別
├── db_manager.py       # 声紋DB（.npz）の読み書き
├── excel_writer.py     # xlwingsによるExcel書き込み
├── vocab_manager.py    # Whisper用語彙管理
├── ai_client.py        # マルチプロバイダーAIクライアント
├── config_manager.py   # 設定の永続化（config.json）
├── supabase_client.py  # Supabaseへのデータ送信
├── viewer/             # Webビューア（別リポジトリで管理）
└── requirements.txt
```

> `voiceprint.npz`（声紋DB）と `config.json`（APIキー）はgit管理対象外です。各環境で個別に作成してください。

---

## 設定値の目安

| パラメータ | デフォルト | 説明 |
|---|---|---|
| PTT閾値 | 0.002 | RMSエネルギーの閾値。有線ノイズに合わせて調整 |
| 話者識別閾値 | 0.75 | コサイン類似度。低いと誤認識増、高いと「不明」増 |
| 最小発言長 | 0.5秒 | これより短いセグメントは無視 |
| AIコンテキスト件数 | 10 | タグ判定に使う直前の発話数 |

---

## 注意事項

- PTTモードは有線接続（イヤホンジャック経由）専用です。Bluetooth接続では動作しません。
- Excel書き込みにはxlwingsを使用しています。ファイルが開かれていると競合する場合があります。
- AI機能はそれぞれのプロバイダーのAPIクレジットを消費します。Geminiの無料枠（gemini-1.5-flash）が費用を抑えやすくおすすめです。
