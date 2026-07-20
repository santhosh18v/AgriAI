import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth-options";
import { fastAnalysisWithGroq } from "@/lib/groq";
import { chatWithGemini } from "@/lib/gemini";

export async function POST(request: NextRequest) {
  try {
    const session = await getServerSession(authOptions);
    if (!session?.user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const { message, provider = "groq", history } = await request.json();

    if (!message) {
      return NextResponse.json({ error: "Message is required" }, { status: 400 });
    }

    let response = "";

    const contextHistory = history
      ?.slice(-5)
      ?.map((h: any) => `${h.role}: ${h.content}`)
      ?.join("\n") || "";

    const fullMessage = contextHistory
      ? `Previous conversation:\n${contextHistory}\n\nCurrent question: ${message}`
      : message;

    if (provider === "groq") {
      response = await fastAnalysisWithGroq(fullMessage);
    } else {
      response = await chatWithGemini(fullMessage);
    }

    return NextResponse.json({ response, provider });
  } catch (error: any) {
    console.error("Chat error:", error);
    return NextResponse.json(
      { error: `Chat failed: ${error?.message || error}` },
      { status: 500 }
    );
  }
}
