import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth-options";
import { analyzeImageWithGemini, chatWithGemini } from "@/lib/gemini";
import { fastAnalysisWithGroq } from "@/lib/groq";
import connectDB from "@/lib/mongodb";
import Analysis from "@/models/Analysis";
import User from "@/models/User";

export async function POST(request: NextRequest) {
  try {
    const session = await getServerSession(authOptions);
    if (!session?.user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const formData = await request.formData();
    const image = formData.get("image") as File | null;
    const query = formData.get("query") as string;
    const type = (formData.get("type") as string) || "general";
    const cropName = formData.get("cropName") as string;
    const provider = (formData.get("provider") as string) || "gemini";

    if (!query) {
      return NextResponse.json({ error: "Query is required" }, { status: 400 });
    }

    let rawResponse = "";
    let aiProvider: "gemini" | "groq" | "combined" = "gemini";

    if (image && provider !== "groq") {
      // Image analysis with Gemini Vision
      const bytes = await image.arrayBuffer();
      const base64 = Buffer.from(bytes).toString("base64");
      const mimeType = image.type as string;

      const prompt = `Analyze this ${type === "crop_disease" ? "crop/plant image" : "agricultural image"} and provide:

1. DIAGNOSIS: What disease, pest, or issue do you see?
2. SEVERITY: Rate as Critical/High/Medium/Low/Healthy
3. CONFIDENCE: Your confidence percentage (0-100)
4. AFFECTED AREA: What percentage of the plant/area is affected?
5. TREATMENT: Step-by-step treatment plan
6. PREVENTION: Future prevention measures
7. EXPERT ADVICE: Should they consult an expert? When?

Additional context from user: "${query}"
${cropName ? `Crop: ${cropName}` : ""}

Please structure your response clearly with these sections.`;

      rawResponse = await analyzeImageWithGemini(base64, mimeType, prompt);
      aiProvider = "gemini";
    } else if (provider === "groq") {
      // Fast text analysis with Groq
      const analysisQuery = `${query}${cropName ? ` (Crop: ${cropName})` : ""}. Type: ${type}`;
      rawResponse = await fastAnalysisWithGroq(analysisQuery);
      aiProvider = "groq";
    } else {
      // Text-based Gemini analysis
      rawResponse = await chatWithGemini(query);
      aiProvider = "gemini";
    }

    // Parse the response into structured data
    const parsed = parseAIResponse(rawResponse);

    // Save to MongoDB
    await connectDB();
    const analysis = await Analysis.create({
      userId: (session.user as any).id,
      type,
      query,
      aiProvider,
      cropName,
      result: {
        ...parsed,
        rawResponse,
      },
      tags: extractTags(query, cropName, type),
    });

    // Increment user analysis count
    await User.findByIdAndUpdate((session.user as any).id, {
      $inc: { analysisCount: 1 },
    });

    return NextResponse.json({
      success: true,
      analysisId: analysis._id,
      result: {
        ...parsed,
        rawResponse,
      },
      aiProvider,
    });
  } catch (error: any) {
    console.error("Analyze error:", error);
    return NextResponse.json(
      { error: `Analysis failed: ${error?.message || error}` },
      { status: 500 }
    );
  }
}

function parseAIResponse(response: string) {
  // Find all matches with their index in the string
  const regex = /(?:^|\n)[#\*\s\-\d\.]*(DIAGNOSIS|SEVERITY|CONFIDENCE|AFFECTED AREA|TREATMENT|PREVENTION|EXPERT ADVICE|EXPERT|CONSULT)[:\s\*\-]*/gi;
  
  const matches: { name: string; index: number; endIndex: number }[] = [];
  let match;
  while ((match = regex.exec(response)) !== null) {
    matches.push({
      name: match[1].toUpperCase(),
      index: match.index,
      endIndex: regex.lastIndex
    });
  }

  // Helper to extract content between a match and the next match
  function getContentForSection(sectionNames: string[]) {
    const found = matches.find(m => sectionNames.includes(m.name));
    if (!found) return null;
    
    // Find the next match that starts after this one
    let nextMatch = null;
    for (const m of matches) {
      if (m.index > found.index) {
        nextMatch = m;
        break;
      }
    }
    
    const start = found.endIndex;
    const end = nextMatch ? nextMatch.index : response.length;
    return response.substring(start, end).trim();
  }

  const diagnosis = getContentForSection(["DIAGNOSIS"]);
  const severityStr = getContentForSection(["SEVERITY"]);
  const confidenceStr = getContentForSection(["CONFIDENCE"]);
  const treatment = getContentForSection(["TREATMENT"]);
  const prevention = getContentForSection(["PREVENTION"]);
  const expertAdvice = getContentForSection(["EXPERT ADVICE", "EXPERT", "CONSULT"]);

  // Extract severity value
  let severity: "critical" | "high" | "medium" | "low" | "healthy" = "medium";
  if (severityStr) {
    const sevMatch = severityStr.match(/(critical|high|medium|low|healthy)/i);
    if (sevMatch) severity = sevMatch[1].toLowerCase() as any;
  }

  // Extract confidence value
  let confidence = 75;
  if (confidenceStr) {
    const confMatch = confidenceStr.match(/(\d+)/);
    if (confMatch) confidence = parseInt(confMatch[1]);
  }

  return {
    diagnosis: diagnosis || extractFirstMeaningfulParagraph(response),
    severity,
    confidence,
    treatment: treatment || "Please consult the full analysis below.",
    prevention: prevention || "Follow standard agricultural best practices.",
    expertAdvice: expertAdvice || undefined,
  };
}

function extractFirstMeaningfulParagraph(text: string): string {
  const lines = text.split("\n").filter((l) => l.trim().length > 20);
  return lines[0] || text.substring(0, 200);
}

function extractTags(query: string, cropName: string, type: string): string[] {
  const tags = [type];
  if (cropName) tags.push(cropName.toLowerCase());
  const keywords = ["disease", "pest", "fungal", "bacterial", "viral", "drought", "irrigation"];
  keywords.forEach((kw) => {
    if (query.toLowerCase().includes(kw)) tags.push(kw);
  });
  return Array.from(new Set(tags));
}
