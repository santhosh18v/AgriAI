/**
 * Maps an approved ML class name into structured crop/condition/healthy
 * fields (Milestone M8, Section 6). This is a fixed lookup table, not an
 * inference -- only the six approved classes are ever accepted (see
 * types.ts's isApprovedClassName), so there is no "unsupported crop"
 * branch to guess at.
 */

import { ApprovedClassName, ClassBreakdown } from "./types";

const CLASS_BREAKDOWN: Record<ApprovedClassName, ClassBreakdown> = {
  "Tomato Healthy": { crop: "Tomato", condition: "Healthy", healthy: true },
  "Tomato Early Blight": { crop: "Tomato", condition: "Early Blight", healthy: false },
  "Tomato Late Blight": { crop: "Tomato", condition: "Late Blight", healthy: false },
  "Potato Healthy": { crop: "Potato", condition: "Healthy", healthy: true },
  "Potato Early Blight": { crop: "Potato", condition: "Early Blight", healthy: false },
  "Potato Late Blight": { crop: "Potato", condition: "Late Blight", healthy: false },
};

export function classBreakdown(className: ApprovedClassName): ClassBreakdown {
  return CLASS_BREAKDOWN[className];
}
