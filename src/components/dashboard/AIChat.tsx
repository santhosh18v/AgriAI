"use client";

import { useState, useRef, useEffect } from "react";
import { Send, Sparkles, Zap, Brain, Loader2, Bot, User } from "lucide-react";
import { useSession } from "next-auth/react";
import { cn } from "@/lib/auth";

interface Message {
  role: "user" | "assistant";
  content: string;
  provider?: string;
}

const suggestedPrompts = [
  "My tomato leaves have brown spots, what could it be?",
  "Best time to irrigate paddy fields in monsoon?",
  "How do I improve sandy soil for vegetable farming?",
  "Natural pest control for aphids on cotton?",
];

export function AIChat() {
  const { data: session } = useSession();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [provider, setProvider] = useState<"groq" | "gemini">("groq");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const sendMessage = async (text: string) => {
    if (!text.trim() || loading) return;

    const userMessage: Message = { role: "user", content: text };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          provider,
          history: messages,
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: "Sorry, I couldn't process that. Please try again." },
        ]);
        return;
      }

      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.response, provider: data.provider },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Something went wrong. Please try again." },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-160px)] glass-card overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-white/5">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-forest-500/15 flex items-center justify-center">
            <Bot className="w-5 h-5 text-forest-400" />
          </div>
          <div>
            <p className="font-semibold text-sm">AgriAI Advisor</p>
            <p className="text-xs text-white/40">Ask anything about farming</p>
          </div>
        </div>

        <div className="flex items-center gap-1 bg-white/5 rounded-lg p-1">
          <button
            onClick={() => setProvider("groq")}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors",
              provider === "groq" ? "bg-orange-500/20 text-orange-400" : "text-white/40"
            )}
          >
            <Zap className="w-3.5 h-3.5" />
            Groq
          </button>
          <button
            onClick={() => setProvider("gemini")}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors",
              provider === "gemini" ? "bg-blue-500/20 text-blue-400" : "text-white/40"
            )}
          >
            <Brain className="w-3.5 h-3.5" />
            Gemini
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center px-4">
            <div className="w-16 h-16 rounded-2xl bg-forest-500/10 flex items-center justify-center mb-4">
              <Sparkles className="w-7 h-7 text-forest-400" />
            </div>
            <h3 className="text-lg font-semibold mb-2">
              Hi {session?.user?.name?.split(" ")[0] || "there"}, how can I help?
            </h3>
            <p className="text-sm text-white/40 max-w-md mb-6">
              Ask me about crop diseases, pest control, soil health, irrigation,
              or anything else related to your farm.
            </p>
            <div className="grid sm:grid-cols-2 gap-2 max-w-lg w-full">
              {suggestedPrompts.map((prompt) => (
                <button
                  key={prompt}
                  onClick={() => sendMessage(prompt)}
                  className="text-left text-sm text-white/60 hover:text-white glass-card-hover p-3"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((msg, i) => (
            <div
              key={i}
              className={cn("flex gap-3 animate-fade-in", msg.role === "user" && "flex-row-reverse")}
            >
              <div
                className={cn(
                  "w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0",
                  msg.role === "user" ? "bg-forest-700/40" : "bg-white/5"
                )}
              >
                {msg.role === "user" ? (
                  <User className="w-4 h-4 text-forest-300" />
                ) : (
                  <Bot className="w-4 h-4 text-white/60" />
                )}
              </div>
              <div
                className={cn(
                  "max-w-[80%] p-4 text-sm leading-relaxed whitespace-pre-line",
                  msg.role === "user" ? "chat-user" : "chat-ai"
                )}
              >
                {msg.content}
                {msg.provider && (
                  <p className="text-[10px] text-white/30 mt-2 flex items-center gap-1">
                    {msg.provider === "groq" ? <Zap className="w-3 h-3" /> : <Brain className="w-3 h-3" />}
                    {msg.provider === "groq" ? "Groq Llama 3" : "Gemini"}
                  </p>
                )}
              </div>
            </div>
          ))
        )}

        {loading && (
          <div className="flex gap-3 animate-fade-in">
            <div className="w-8 h-8 rounded-lg bg-white/5 flex items-center justify-center flex-shrink-0">
              <Bot className="w-4 h-4 text-white/60" />
            </div>
            <div className="chat-ai p-4 flex items-center gap-2">
              <Loader2 className="w-4 h-4 animate-spin text-forest-400" />
              <span className="text-sm text-white/40">Thinking...</span>
            </div>
          </div>
        )}
        <div ref={scrollRef} />
      </div>

      {/* Input */}
      <div className="p-4 border-t border-white/5">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            sendMessage(input);
          }}
          className="flex items-center gap-3"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about crops, pests, soil, weather..."
            className="input-field flex-1"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="btn-primary px-4 py-3 disabled:opacity-50"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
      </div>
    </div>
  );
}
