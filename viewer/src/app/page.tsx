"use client";

export const dynamic = "force-dynamic";

import { useEffect, useRef, useState, useCallback } from "react";
import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";
const supabase =
  supabaseUrl && supabaseKey
    ? createClient(supabaseUrl, supabaseKey)
    : null;

type Utterance = {
  id: number;
  session_id: string;
  created_at: string;
  ts: string;
  speaker: string;
  text: string;
  tag: string;
  summary: string;
  status: string; // "pending" | "processing" | "done" | "error"
};

const SPEAKER_COLORS = [
  "bg-blue-100 text-blue-800",
  "bg-green-100 text-green-800",
  "bg-purple-100 text-purple-800",
  "bg-orange-100 text-orange-800",
  "bg-pink-100 text-pink-800",
  "bg-teal-100 text-teal-800",
  "bg-red-100 text-red-800",
  "bg-yellow-100 text-yellow-800",
  "bg-indigo-100 text-indigo-800",
  "bg-gray-100 text-gray-800",
];

function useSpeakerColor() {
  const map = useRef<Record<string, string>>({});
  const counter = useRef(0);
  return (speaker: string) => {
    if (!map.current[speaker]) {
      map.current[speaker] =
        SPEAKER_COLORS[counter.current % SPEAKER_COLORS.length];
      counter.current++;
    }
    return map.current[speaker];
  };
}

// TSV形式でExcelに貼り付けられる文字列を生成
function toTsv(utterances: Utterance[]): string {
  const headers = ["時刻", "話者", "発言内容", "タグ", "要約"];
  const escape = (v: string) => {
    if (/[\t\n"]/.test(v)) return `"${v.replace(/"/g, '""')}"`;
    return v;
  };
  const rows = utterances
    .filter((u) => u.status === "done")
    .map((u) =>
      [u.ts, u.speaker, u.text, u.tag, u.summary].map(escape).join("\t")
    );
  return [headers.join("\t"), ...rows].join("\n");
}

export default function Home() {
  const [utterances, setUtterances] = useState<Utterance[]>([]);
  const [sessions, setSessions] = useState<string[]>([]);
  const [selectedSession, setSelectedSession] = useState<string>("latest");
  const [autoScroll, setAutoScroll] = useState(true);
  const [connected, setConnected] = useState(false);
  const [copied, setCopied] = useState(false);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [showSessionModal, setShowSessionModal] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const getSpeakerColor = useSpeakerColor();
  const processingRef = useRef<Set<number>>(new Set());
  const utterancesRef = useRef<Utterance[]>([]);

  // 短いセッションID生成（6文字・紛らわしい文字を除外）
  const generateSessionId = () => {
    const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
    return Array.from({ length: 6 }, () =>
      chars[Math.floor(Math.random() * chars.length)]
    ).join("");
  };

  const handleNewSession = () => {
    const newId = generateSessionId();
    setActiveSessionId(newId);
    setSelectedSession(newId);
    setShowSessionModal(true);
  };

  // utterancesRefを常に最新に保つ
  useEffect(() => {
    utterancesRef.current = utterances;
  }, [utterances]);

  // pending utteranceをAPIルートに送って処理
  const processUtterance = useCallback(async (u: Utterance) => {
    if (processingRef.current.has(u.id)) return;
    processingRef.current.add(u.id);

    const context = utterancesRef.current
      .filter((x) => x.status === "done")
      .slice(-10)
      .map(({ tag, speaker, text }) => ({ tag, speaker, text }));

    try {
      await fetch("/api/process", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: u.id, context }),
      });
    } catch (e) {
      console.error("[process]", e);
    } finally {
      processingRef.current.delete(u.id);
    }
  }, []);

  // セッション一覧を取得
  useEffect(() => {
    if (!supabase) return;
    supabase
      .from("utterances")
      .select("session_id, created_at")
      .order("created_at", { ascending: false })
      .then(({ data }) => {
        if (!data) return;
        const seen = new Set<string>();
        const unique: string[] = [];
        for (const row of data) {
          if (!seen.has(row.session_id)) {
            seen.add(row.session_id);
            unique.push(row.session_id);
          }
        }
        setSessions(unique);
      });
  }, []);

  // 発話を取得（セッション切替時）
  useEffect(() => {
    if (!supabase) return;
    let query = supabase
      .from("utterances")
      .select("*")
      .order("created_at", { ascending: true });

    if (selectedSession !== "latest") {
      query = query.eq("session_id", selectedSession);
    } else {
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      query = query.gte("created_at", today.toISOString());
    }

    query.then(({ data }) => {
      const rows = data ?? [];
      setUtterances(rows);
      // 未処理のpendingを再トリガー
      rows
        .filter((u) => u.status === "pending")
        .forEach(processUtterance);
    });
  }, [selectedSession, processUtterance]);

  // リアルタイム購読（INSERT / UPDATE）
  useEffect(() => {
    if (!supabase) return;

    const channel = supabase
      .channel("utterances-realtime")
      .on(
        "postgres_changes",
        { event: "INSERT", schema: "public", table: "utterances" },
        (payload) => {
          const row = payload.new as Utterance;
          if (
            selectedSession === "latest" ||
            row.session_id === selectedSession
          ) {
            setUtterances((prev) => [...prev, row]);
            setSessions((prev) =>
              prev.includes(row.session_id)
                ? prev
                : [row.session_id, ...prev]
            );
            if (row.status === "pending") processUtterance(row);
          }
        }
      )
      .on(
        "postgres_changes",
        { event: "UPDATE", schema: "public", table: "utterances" },
        (payload) => {
          const row = payload.new as Utterance;
          setUtterances((prev) =>
            prev.map((u) => (u.id === row.id ? row : u))
          );
        }
      )
      .subscribe((status) => {
        setConnected(status === "SUBSCRIBED");
      });

    return () => {
      supabase.removeChannel(channel);
    };
  }, [selectedSession, processUtterance]);

  // 自動スクロール
  useEffect(() => {
    if (autoScroll) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [utterances, autoScroll]);

  // Excelコピー
  const handleCopy = () => {
    navigator.clipboard.writeText(toTsv(utterances)).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      {/* ヘッダー */}
      <header className="bg-white border-b px-4 py-2 flex items-center gap-3 flex-wrap shadow-sm">
        <h1 className="text-base font-bold text-gray-800 whitespace-nowrap">
          📻 トランシーバ記録ビューア
        </h1>

        <span
          className={`text-xs px-2 py-0.5 rounded-full font-medium ${
            connected
              ? "bg-green-100 text-green-700"
              : "bg-gray-100 text-gray-500"
          }`}
        >
          {connected ? "● リアルタイム接続中" : "○ 接続中..."}
        </span>

        <div className="flex items-center gap-2 ml-auto flex-wrap">
          {/* セッション選択 */}
          <label className="text-xs text-gray-600">セッション：</label>
          <select
            className="text-xs border rounded px-2 py-1 bg-white"
            value={selectedSession}
            onChange={(e) => setSelectedSession(e.target.value)}
          >
            <option value="latest">本日すべて</option>
            {sessions.map((s) => (
              <option key={s} value={s}>
                {s.slice(0, 8)}…
              </option>
            ))}
          </select>

          {/* 自動スクロール */}
          <label className="flex items-center gap-1 text-xs text-gray-600 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
              className="rounded"
            />
            最新へ自動スクロール
          </label>

          {/* 新しい会話ボタン */}
          <button
            onClick={handleNewSession}
            className="text-xs px-3 py-1 rounded border font-medium bg-white border-gray-300 text-gray-700 hover:bg-gray-100"
          >
            ＋ 新しい会話
          </button>

          {/* Excelコピーボタン */}
          <button
            onClick={handleCopy}
            className={`text-xs px-3 py-1 rounded border font-medium transition-colors ${
              copied
                ? "bg-green-100 border-green-400 text-green-700"
                : "bg-white border-gray-300 text-gray-700 hover:bg-gray-100"
            }`}
          >
            {copied ? "✓ コピー済" : "📋 Excelにコピー"}
          </button>

          <span className="text-xs text-gray-400">
            {utterances.filter((u) => u.status === "done").length}件
          </span>
        </div>
      </header>

      {/* テーブル */}
      <div className="flex-1 overflow-auto">
        <table className="w-full text-sm border-collapse">
          <thead className="bg-gray-100 sticky top-0 z-10">
            <tr>
              <th className="px-3 py-2 text-left font-semibold text-gray-600 w-20 border-b whitespace-nowrap">
                時刻
              </th>
              <th className="px-3 py-2 text-left font-semibold text-gray-600 w-24 border-b whitespace-nowrap">
                話者
              </th>
              <th className="px-3 py-2 text-left font-semibold text-gray-600 border-b">
                発言内容
              </th>
              <th className="px-3 py-2 text-left font-semibold text-gray-600 w-16 border-b whitespace-nowrap">
                タグ
              </th>
              <th className="px-3 py-2 text-left font-semibold text-gray-600 w-56 border-b whitespace-nowrap">
                要約
              </th>
            </tr>
          </thead>
          <tbody>
            {utterances.length === 0 ? (
              <tr>
                <td colSpan={5} className="text-center py-16 text-gray-400">
                  発話がありません。記録を開始してください。
                </td>
              </tr>
            ) : (
              utterances.map((u, i) => {
                const isPending =
                  u.status === "pending" || u.status === "processing";
                const isError = u.status === "error";
                return (
                  <tr
                    key={u.id}
                    className={`border-b transition-colors ${
                      isPending
                        ? "bg-yellow-50"
                        : isError
                        ? "bg-red-50"
                        : i % 2 === 0
                        ? "bg-white hover:bg-blue-50"
                        : "bg-gray-50 hover:bg-blue-50"
                    }`}
                  >
                    {/* 時刻 */}
                    <td className="px-3 py-2 text-gray-500 font-mono text-xs whitespace-nowrap align-top">
                      {u.ts}
                    </td>
                    {/* 話者 */}
                    <td className="px-3 py-2 align-top">
                      <span
                        className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${getSpeakerColor(
                          u.speaker
                        )}`}
                      >
                        {u.speaker}
                      </span>
                    </td>
                    {/* 発言内容 */}
                    <td className="px-3 py-2 text-gray-800 align-top max-w-sm">
                      {isPending ? (
                        <span className="flex items-center gap-2 text-yellow-600 text-xs">
                          <svg
                            className="animate-spin h-3 w-3"
                            viewBox="0 0 24 24"
                            fill="none"
                          >
                            <circle
                              className="opacity-25"
                              cx="12"
                              cy="12"
                              r="10"
                              stroke="currentColor"
                              strokeWidth="4"
                            />
                            <path
                              className="opacity-75"
                              fill="currentColor"
                              d="M4 12a8 8 0 018-8v8H4z"
                            />
                          </svg>
                          ☁ Web処理中...
                        </span>
                      ) : (
                        <span className="whitespace-pre-wrap break-words">
                          {u.text}
                        </span>
                      )}
                    </td>
                    {/* タグ */}
                    <td className="px-3 py-2 text-gray-500 font-mono text-xs align-top whitespace-nowrap">
                      {u.tag}
                    </td>
                    {/* 要約 */}
                    <td className="px-3 py-2 text-gray-600 text-xs align-top">
                      <span className="whitespace-pre-wrap break-words">
                        {u.summary}
                      </span>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
        <div ref={bottomRef} />
      </div>

      {/* セッションIDモーダル */}
      {showSessionModal && activeSessionId && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl p-8 w-80 text-center">
            <p className="text-sm text-gray-500 mb-3">新しい会話IDを発行しました</p>
            <div className="bg-gray-100 rounded-lg py-5 px-4 mb-4">
              <span className="text-4xl font-bold tracking-[0.3em] text-gray-800 font-mono select-all">
                {activeSessionId}
              </span>
            </div>
            <p className="text-xs text-gray-500 mb-6">
              このIDをローカルアプリのセッションID欄に入力してください
            </p>
            <button
              onClick={() => setShowSessionModal(false)}
              className="w-full py-2 bg-blue-500 text-white rounded-lg font-medium hover:bg-blue-600 transition-colors"
            >
              OK
            </button>
          </div>
        </div>
      )}

      {/* フッター */}
      <footer className="bg-white border-t px-4 py-1 text-xs text-gray-400 text-right">
        トランシーバ記録システム — ブラウザビューア
      </footer>
    </div>
  );
}
