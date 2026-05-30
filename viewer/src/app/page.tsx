"use client";

import { useEffect, useRef, useState } from "react";
import { createClient } from "@supabase/supabase-js";

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
);

type Utterance = {
  id: number;
  session_id: string;
  created_at: string;
  ts: string;
  speaker: string;
  text: string;
  tag: string;
  summary: string;
};

// 話者ごとの色（最大10名）
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

export default function Home() {
  const [utterances, setUtterances] = useState<Utterance[]>([]);
  const [sessions, setSessions] = useState<string[]>([]);
  const [selectedSession, setSelectedSession] = useState<string>("latest");
  const [autoScroll, setAutoScroll] = useState(true);
  const [connected, setConnected] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const getSpeakerColor = useSpeakerColor();

  // セッション一覧を取得
  useEffect(() => {
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
    let query = supabase
      .from("utterances")
      .select("*")
      .order("created_at", { ascending: true });

    if (selectedSession !== "latest") {
      query = query.eq("session_id", selectedSession);
    } else {
      // 最新セッション：当日分すべて
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      query = query.gte("created_at", today.toISOString());
    }

    query.then(({ data }) => {
      setUtterances(data ?? []);
    });
  }, [selectedSession]);

  // リアルタイム購読
  useEffect(() => {
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
          }
        }
      )
      .subscribe((status) => {
        setConnected(status === "SUBSCRIBED");
      });

    return () => {
      supabase.removeChannel(channel);
    };
  }, [selectedSession]);

  // 自動スクロール
  useEffect(() => {
    if (autoScroll) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [utterances, autoScroll]);

  return (
    <div className="flex flex-col h-screen">
      {/* ヘッダー */}
      <header className="bg-white border-b px-4 py-3 flex items-center gap-4 flex-wrap shadow-sm">
        <h1 className="text-lg font-bold text-gray-800 whitespace-nowrap">
          📻 トランシーバ記録ビューア
        </h1>

        {/* 接続状態 */}
        <span
          className={`text-xs px-2 py-1 rounded-full font-medium ${
            connected
              ? "bg-green-100 text-green-700"
              : "bg-gray-100 text-gray-500"
          }`}
        >
          {connected ? "● リアルタイム接続中" : "○ 接続中..."}
        </span>

        {/* セッション選択 */}
        <div className="flex items-center gap-2 ml-auto flex-wrap">
          <label className="text-sm text-gray-600">セッション：</label>
          <select
            className="text-sm border rounded px-2 py-1 bg-white"
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
          <label className="flex items-center gap-1 text-sm text-gray-600 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
              className="rounded"
            />
            最新へ自動スクロール
          </label>

          <span className="text-xs text-gray-400">{utterances.length}件</span>
        </div>
      </header>

      {/* テーブル */}
      <div className="flex-1 overflow-auto">
        <table className="w-full text-sm border-collapse">
          <thead className="bg-gray-100 sticky top-0 z-10">
            <tr>
              <th className="px-3 py-2 text-left font-semibold text-gray-600 w-20 border-b">時刻</th>
              <th className="px-3 py-2 text-left font-semibold text-gray-600 w-24 border-b">話者</th>
              <th className="px-3 py-2 text-left font-semibold text-gray-600 border-b">発言内容</th>
              <th className="px-3 py-2 text-left font-semibold text-gray-600 w-16 border-b">タグ</th>
              <th className="px-3 py-2 text-left font-semibold text-gray-600 w-52 border-b">要約</th>
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
              utterances.map((u, i) => (
                <tr
                  key={u.id}
                  className={`border-b hover:bg-blue-50 transition-colors ${
                    i % 2 === 0 ? "bg-white" : "bg-gray-50"
                  }`}
                >
                  <td className="px-3 py-2 text-gray-500 font-mono text-xs whitespace-nowrap">
                    {u.ts}
                  </td>
                  <td className="px-3 py-2">
                    <span
                      className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${getSpeakerColor(
                        u.speaker
                      )}`}
                    >
                      {u.speaker}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-gray-800">{u.text}</td>
                  <td className="px-3 py-2 text-gray-500 font-mono text-xs">
                    {u.tag}
                  </td>
                  <td className="px-3 py-2 text-gray-600 text-xs">{u.summary}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
        <div ref={bottomRef} />
      </div>

      {/* フッター */}
      <footer className="bg-white border-t px-4 py-2 text-xs text-gray-400 text-right">
        トランシーバ記録システム — 閲覧専用
      </footer>
    </div>
  );
}
