import Groq from "groq-sdk";

const groq = new Groq({
  apiKey: process.env.GROQ_API_KEY!,
});

export async function fastAnalysisWithGroq(
  message: string,
  systemPrompt?: string
): Promise<string> {
  try {
    const system = systemPrompt || `You are AgriAI's fast analysis engine. You specialize in:
    - Rapid crop disease diagnosis
    - Quick pest identification  
    - Fast soil health assessment
    - Immediate environmental risk alerts
    - Weather impact on crops
    
    Provide structured responses with:
    - DIAGNOSIS: (what you found)
    - SEVERITY: (Critical/High/Medium/Low)
    - CONFIDENCE: (percentage)
    - IMMEDIATE ACTION: (what to do now)
    - TREATMENT: (detailed steps)
    - PREVENTION: (future measures)
    
    Be concise but comprehensive. Use farmer-friendly language.`;

    const completion = await groq.chat.completions.create({
      messages: [
        { role: "system", content: system },
        { role: "user", content: message },
      ],
      model: "llama-3.3-70b-versatile",
      temperature: 0.3,
      max_tokens: 1024,
      stream: false,
    });

    return completion.choices[0]?.message?.content || "No response generated";
  } catch (error: any) {
    console.error("Groq error:", error);
    throw new Error(`Failed to get response from Groq: ${error?.message || error}`);
  }
}

export async function streamGroqResponse(
  message: string,
  onChunk: (text: string) => void
): Promise<void> {
  try {
    const stream = await groq.chat.completions.create({
      messages: [
        {
          role: "system",
          content: `You are AgriAI, an agricultural intelligence assistant. Provide helpful, accurate farming advice.`,
        },
        { role: "user", content: message },
      ],
      model: "llama-3.1-8b-instant",
      temperature: 0.5,
      max_tokens: 800,
      stream: true,
    });

    for await (const chunk of stream) {
      const text = chunk.choices[0]?.delta?.content || "";
      if (text) onChunk(text);
    }
  } catch (error: any) {
    console.error("Groq stream error:", error);
    throw new Error(`Streaming failed: ${error?.message || error}`);
  }
}
