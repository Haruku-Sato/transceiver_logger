import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import OpenAI from "openai";

const SYSTEM_PROMPT = `あなたは無線通話ログのAIアシスタントです。
ユーザーから直前の発話リストと新しい発話が与えられます。
以下の形式でJSONのみを返してください（説明文不要）：
{"summary": "1文以内の簡潔な要約", "tag": "X.Y.Z"}

タグのルール：
- タグはLaTeXのセクション番号形式（1, 1.1, 1.1.1, 1.2, 2 など）
- 前後の発話と話題のつながりがある場合は同じ親タグを持つ番号を割り当てる
- 全く新しい話題なら新しい番号（2, 3 ...）を割り当てる
- 最初の発話は 1 から始める
- タグは文字列として返す（例: "1.2.3"）`;

function getSupabase() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
  );
}

function getOpenAI() {
  return new OpenAI({ apiKey: process.env.OPENAI_API_KEY });
}

export async function POST(req: NextRequest) {
  const supabase = getSupabase();
  const openai = getOpenAI();

  let id: number;
  let context: { tag: string; speaker: string; text: string }[] = [];

  try {
    ({ id, context = [] } = await req.json());
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }

  // 処理中にマーク（二重処理防止）
  const { data: updated } = await supabase
    .from("utterances")
    .update({ status: "processing" })
    .eq("id", id)
    .eq("status", "pending")
    .select()
    .single();

  if (!updated) {
    return NextResponse.json({ error: "not pending or not found" }, { status: 409 });
  }

  try {
    // 音声をStorageからダウンロード
    const { data: audioBlob, error: storageErr } = await supabase.storage
      .from("audio")
      .download(updated.audio_path);

    if (storageErr || !audioBlob) {
      throw new Error(`Storage download failed: ${storageErr?.message}`);
    }

    // Whisper API で文字起こし
    const audioBuffer = Buffer.from(await audioBlob.arrayBuffer());
    const transcription = await openai.audio.transcriptions.create({
      file: new File([audioBuffer], "audio.wav", { type: "audio/wav" }),
      model: "whisper-1",
      language: "ja",
    });
    const text = transcription.text.trim();

    // AI 要約・タグ付け
    let tag = "";
    let summary = "";
    if (text) {
      let userMsg = "";
      if (context.length > 0) {
        userMsg += "【直前の発話リスト】\n";
        context.forEach((item, i) => {
          userMsg += `${i + 1}. [${item.tag}] ${item.speaker}: ${item.text}\n`;
        });
        userMsg += "\n";
      }
      userMsg += `【新しい発話】\n${text}`;

      const completion = await openai.chat.completions.create({
        model: "gpt-4o-mini",
        messages: [
          { role: "system", content: SYSTEM_PROMPT },
          { role: "user", content: userMsg },
        ],
        temperature: 0.2,
        response_format: { type: "json_object" },
      });

      try {
        const aiResult = JSON.parse(
          completion.choices[0].message.content ?? "{}"
        );
        tag = String(aiResult.tag ?? "");
        summary = String(aiResult.summary ?? "");
      } catch {}
    }

    // DB 更新
    await supabase
      .from("utterances")
      .update({ text, tag, summary, status: "done" })
      .eq("id", id);

    // 音声ファイル削除
    await supabase.storage.from("audio").remove([updated.audio_path]);

    return NextResponse.json({ ok: true, text, tag, summary });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    console.error("[process]", msg);
    await supabase
      .from("utterances")
      .update({ status: "error", text: `処理エラー: ${msg}` })
      .eq("id", id);
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
