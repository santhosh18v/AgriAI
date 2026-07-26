import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth-options";
import { analyzeImageWithGemini, chatWithGemini } from "@/lib/gemini";
import { fastAnalysisWithGroq } from "@/lib/groq";
import connectDB from "@/lib/mongodb";
import Analysis from "@/models/Analysis";
import User from "@/models/User";
import { parseAIResponse } from "@/lib/disease-analysis/providers/gemini";
import { runDiseaseAnalysis } from "@/lib/disease-analysis/service";
import { getDiseaseAnalysisConfig, DiseaseAnalysisConfigError } from "@/lib/disease-analysis/config";
import { DiseaseAnalysisError, DiseaseAnalysisOutcome } from "@/lib/disease-analysis/types";

type PersistedAiProvider = "gemini" | "groq" | "combined" | "custom-ml";

/**
 * Milestone M8: determines the honest `Analysis.aiProvider` value for a
 * completed custom-ml-flow outcome (see Analysis.ts's schema comment).
 * - Only Gemini ever produced usable content (full infrastructure
 *   fallback -- predictWithCustomMl never returned data) -> "gemini".
 * - Only the custom-ml model produced the returned result (accepted or
 *   uncertain, no secondary opinion attached) -> "custom-ml".
 * - Both custom-ml (primary, uncertain) AND Gemini (secondary opinion)
 *   genuinely contributed -> "combined" -- never used for a single-source
 *   result.
 */
function resolveDiseaseOutcomeAiProvider(outcome: DiseaseAnalysisOutcome): PersistedAiProvider {
  if (outcome.secondaryOpinion) return "combined";
  if (outcome.customMl) return "custom-ml";
  return "gemini";
}

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
    let aiProvider: PersistedAiProvider = "gemini";
    let diseaseOutcome: DiseaseAnalysisOutcome | null = null;

    // Milestone M8: the custom ML disease-prediction service is only ever
    // considered for the crop-disease image-analysis case, and only when
    // explicitly selected via server-side configuration -- every other
    // existing path (pest/soil/weather/waste image analysis, Groq, and
    // text-only Gemini) is completely unchanged below.
    let useCustomMlFlow = false;
    if (image && provider !== "groq" && type === "crop_disease") {
      try {
        useCustomMlFlow = getDiseaseAnalysisConfig().provider === "custom-ml";
      } catch (configError) {
        if (configError instanceof DiseaseAnalysisConfigError) {
          console.error("Disease analysis configuration error:", configError.message);
          return NextResponse.json(
            {
              success: false,
              error: {
                code: "DISEASE_ANALYSIS_FAILED",
                message: "Disease analysis is temporarily unavailable.",
              },
            },
            { status: 500 }
          );
        }
        throw configError;
      }
    }

    if (useCustomMlFlow) {
      try {
        diseaseOutcome = await runDiseaseAnalysis({ file: image as File, query, cropName });
        rawResponse = diseaseOutcome.legacy.rawResponse;
      } catch (err) {
        if (err instanceof DiseaseAnalysisError) {
          console.error("Disease analysis provider error:", err.code, err.message);
          return NextResponse.json(
            { success: false, error: { code: err.code, message: err.message } },
            { status: err.httpStatus }
          );
        }
        throw err;
      }
    } else if (image && provider !== "groq") {
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

    // Parse the response into structured data (already parsed for the
    // custom-ml flow -- diseaseOutcome.legacy is used directly there).
    const parsed = diseaseOutcome
      ? {
          diagnosis: diseaseOutcome.legacy.diagnosis,
          severity: diseaseOutcome.legacy.severity,
          confidence: diseaseOutcome.legacy.confidence,
          treatment: diseaseOutcome.legacy.treatment,
          prevention: diseaseOutcome.legacy.prevention,
          expertAdvice: diseaseOutcome.legacy.expertAdvice,
        }
      : parseAIResponse(rawResponse);

    // Milestone M8: every completed analysis is persisted, exactly as
    // before M8 -- custom-ml results are no longer silently skipped (that
    // would be a regression: every other request type has always been
    // saved to history). `aiProvider` is resolved to an honest value that
    // reflects what actually produced the result (see
    // resolveDiseaseOutcomeAiProvider above); "combined" is only used when
    // both custom-ml and Gemini genuinely contributed.
    if (diseaseOutcome) {
      aiProvider = resolveDiseaseOutcomeAiProvider(diseaseOutcome);
    }

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
    const analysisId: string = analysis._id;

    // Increment user analysis count -- only reached after Analysis.create()
    // succeeds; a persistence failure above throws and is handled by the
    // outer try/catch, which never increments the count and never returns
    // success:true (unchanged from pre-M8 behavior).
    await User.findByIdAndUpdate((session.user as any).id, {
      $inc: { analysisCount: 1 },
    });

    const customMl = diseaseOutcome?.customMl;

    return NextResponse.json({
      success: true,
      analysisId,
      result: {
        ...parsed,
        rawResponse,
        ...(customMl
          ? {
              modelConfidence: customMl.modelConfidence,
              accepted: customMl.accepted,
              uncertain: customMl.uncertain,
              confidenceLabel: customMl.confidenceLabel,
              productionCalibrated: customMl.productionCalibrated,
              supportedClass: customMl.supportedClass,
              crop: customMl.crop,
              condition: customMl.condition,
              healthy: customMl.healthy,
              topPredictions: customMl.topPredictions,
            }
          : {}),
      },
      aiProvider: diseaseOutcome ? diseaseOutcome.provider : aiProvider,
      ...(customMl ? { source: { provider: "custom-ml", model: "efficientnet_b0", classCount: 6 } } : {}),
      ...(customMl ? { limitations: customMl.limitations } : {}),
      ...(diseaseOutcome?.fallback ? { fallback: diseaseOutcome.fallback } : {}),
      ...(diseaseOutcome?.secondaryOpinion
        ? {
            secondaryOpinion: {
              provider: diseaseOutcome.secondaryOpinion.provider,
              result: diseaseOutcome.secondaryOpinion.legacy,
            },
          }
        : {}),
    });
  } catch (error: any) {
    console.error("Analyze error:", error);
    return NextResponse.json(
      { error: `Analysis failed: ${error?.message || error}` },
      { status: 500 }
    );
  }
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
