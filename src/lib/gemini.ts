import { GoogleGenerativeAI } from "@google/generative-ai";

const rawKey = process.env.GEMINI_API_KEY || "";
const cleanKey = rawKey.replace(/^["']|["']$/g, "");
const genAI = new GoogleGenerativeAI(cleanKey);

export const geminiModel = genAI.getGenerativeModel({ model: "gemini-2.5-flash" });
export const geminiVisionModel = genAI.getGenerativeModel({ model: "gemini-2.5-flash" });

export async function analyzeImageWithGemini(
  imageBase64: string,
  mimeType: string,
  prompt: string
): Promise<string> {
  try {
    const imagePart = {
      inlineData: {
        data: imageBase64,
        mimeType,
      },
    };

    const result = await geminiVisionModel.generateContent([prompt, imagePart]);
    const response = await result.response;
    return response.text();
  } catch (error: any) {
    console.error("Gemini vision error:", error);
    throw new Error(`Failed to analyze image with Gemini: ${error?.message || error}`);
  }
}

export async function chatWithGemini(
  message: string,
  context?: string
): Promise<string> {
  try {
    const systemContext = context || `You are AgriAI, an expert agricultural and environmental intelligence assistant. 
    You help farmers, gardeners, and environmental workers with:
    - Crop disease detection and treatment advice
    - Pest identification and management
    - Soil health analysis and improvement
    - Weather-based farming guidance
    - Sustainable farming practices
    - Waste management solutions
    - Irrigation optimization
    
    Always provide:
    1. Clear diagnosis/identification
    2. Confidence level (High/Medium/Low)
    3. Step-by-step actionable advice
    4. When to seek expert help
    5. Preventive measures for future
    
    Keep responses practical, farmer-friendly, and in simple language.`;

    const fullPrompt = `${systemContext}\n\nUser question: ${message}`;
    const result = await geminiModel.generateContent(fullPrompt);
    const response = await result.response;
    return response.text();
  } catch (error: any) {
    console.error("Gemini chat error:", error);
    throw new Error(`Failed to get response from Gemini: ${error?.message || error}`);
  }
}
