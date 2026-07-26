/**
 * Gemini provider wrapper for disease analysis (Milestone M8).
 *
 * `src/lib/gemini.ts` (the Gemini SDK wrapper -- analyzeImageWithGemini,
 * chatWithGemini) is unchanged and untouched by M8. This module only
 * houses the response-shaping logic that turns Gemini's raw text into the
 * app's existing result shape -- moved here verbatim from
 * src/app/api/analyze/route.ts (not rewritten), since it's naturally
 * "Gemini provider" output-shaping, not route-handling. The prompt-
 * building logic for the general (non-disease-specific) `/api/analyze`
 * flow stays in route.ts unchanged, since it varies by analysis `type`
 * (crop_disease/pest/soil/weather/waste) and this module must not change
 * behavior for any of those existing, non-M8 call sites.
 */

import { LegacyAnalysisResult } from "../types";

export function parseAIResponse(response: string): Omit<LegacyAnalysisResult, "rawResponse"> {
  // Find all matches with their index in the string
  const regex =
    /(?:^|\n)[#\*\s\-\d\.]*(DIAGNOSIS|SEVERITY|CONFIDENCE|AFFECTED AREA|TREATMENT|PREVENTION|EXPERT ADVICE|EXPERT|CONSULT)[:\s\*\-]*/gi;

  const matches: { name: string; index: number; endIndex: number }[] = [];
  let match;
  while ((match = regex.exec(response)) !== null) {
    matches.push({
      name: match[1].toUpperCase(),
      index: match.index,
      endIndex: regex.lastIndex,
    });
  }

  // Helper to extract content between a match and the next match
  function getContentForSection(sectionNames: string[]) {
    const found = matches.find((m) => sectionNames.includes(m.name));
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
