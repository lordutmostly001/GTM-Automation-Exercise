"""
persona_generation/confidence_checker.py
=========================================
Validates LLM persona outputs before they enter the outreach pipeline.

Two layers of checking:
  1. Structural — did the LLM return valid JSON with all required fields?
  2. Semantic  — is the content specific enough, or is it generic filler?

A contact flagged LOW confidence is routed to human review queue.
It is NEVER sent to outreach automatically.

Design rationale:
  Bad personalization is worse than no personalization.
  A generic "As a leader in the tech space..." email destroys credibility.
  Better to hold 10% of contacts for manual review than to send 200 bad emails.
"""

import re
import json
import logging

log = logging.getLogger(__name__)

# ── Generic phrase blacklist (from config, reproduced here for portability) ───

GENERIC_PHRASES = [
    "as a leader", "in the tech space", "passionate about",
    "driving innovation", "thought leader", "seasoned professional",
    "dynamic", "visionary", "at the forefront", "ecosystem",
    "leveraging technology", "disrupting the", "game changer",
    "cutting edge", "best in class", "world class", "next level",
]

# ── Minimum length thresholds ─────────────────────────────────────────────────

MIN_PERSONA_CHARS  = 80
MIN_HOOK_CHARS     = 50
MIN_THEME_CHARS    = 20
REQUIRED_THEMES    = 2  # at least 2 of 3 themes must be non-empty


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURAL VALIDATION
# ─────────────────────────────────────────────────────────────────────────────

def parse_llm_output(raw_output: str) -> tuple[dict | None, str]:
    """
    Parse raw LLM string into a dict.
    Handles common LLM quirks: markdown fences, leading text, trailing commas.

    Returns:
        (parsed_dict, error_message)
        If successful: (dict, "")
        If failed:     (None, reason)
    """
    if not raw_output or not raw_output.strip():
        return None, "Empty response from LLM"

    text = raw_output.strip()

    # Strip markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    # Find the first { and last } to extract JSON object
    start = text.find("{")
    end   = text.rfind("}")
    if start == -1 or end == -1:
        return None, f"No JSON object found in output: {text[:100]}"

    text = text[start:end+1]

    # Fix trailing commas before } or ] (common LLM mistake)
    text = re.sub(r",\s*([}\]])", r"\1", text)

    try:
        parsed = json.loads(text)
        return parsed, ""
    except json.JSONDecodeError as e:
        return None, f"JSON parse error: {e} — raw: {text[:200]}"


def validate_structure(parsed: dict) -> tuple[bool, list[str]]:
    """
    Check all required fields are present and non-empty.

    Returns:
        (is_valid, list_of_issues)
    """
    issues = []
    required = ["persona_summary", "context_hook", "personalization_themes", "confidence"]

    for field in required:
        if field not in parsed:
            issues.append(f"Missing field: {field}")
        elif not parsed[field]:
            issues.append(f"Empty field: {field}")

    if "personalization_themes" in parsed:
        themes = parsed["personalization_themes"]
        if not isinstance(themes, list):
            issues.append("personalization_themes must be a list")
        elif len(themes) < REQUIRED_THEMES:
            issues.append(f"Need at least {REQUIRED_THEMES} themes, got {len(themes)}")

    if "confidence" in parsed:
        if parsed["confidence"] not in ("HIGH", "MEDIUM", "LOW"):
            issues.append(f"Invalid confidence value: {parsed['confidence']}")

    return len(issues) == 0, issues


# ─────────────────────────────────────────────────────────────────────────────
# SEMANTIC VALIDATION
# ─────────────────────────────────────────────────────────────────────────────

def check_generic_phrases(text: str) -> list[str]:
    """Return list of blacklisted generic phrases found in text."""
    text_lower = text.lower()
    return [phrase for phrase in GENERIC_PHRASES if phrase in text_lower]


def check_specificity(parsed: dict, contact: dict) -> tuple[str, list[str]]:
    """
    Assess whether persona content is specific enough to this contact.

    Checks:
      - Minimum length of each field
      - Absence of blacklisted generic phrases
      - Whether contact's company/title is referenced (signal of specificity)
      - Whether the LLM itself flagged LOW confidence

    Returns:
        (final_confidence: 'HIGH'|'MEDIUM'|'LOW', reasons: list)
    """
    reasons = []
    flags   = 0

    persona = str(parsed.get("persona_summary", ""))
    hook    = str(parsed.get("context_hook", ""))
    themes  = parsed.get("personalization_themes", [])

    # ── Length checks ──────────────────────────────────────────────────────
    if len(persona) < MIN_PERSONA_CHARS:
        reasons.append(f"persona_summary too short ({len(persona)} chars, min {MIN_PERSONA_CHARS})")
        flags += 1

    if len(hook) < MIN_HOOK_CHARS:
        reasons.append(f"context_hook too short ({len(hook)} chars, min {MIN_HOOK_CHARS})")
        flags += 1

    short_themes = [t for t in themes if len(str(t)) < MIN_THEME_CHARS]
    if short_themes:
        reasons.append(f"{len(short_themes)} theme(s) too short")
        flags += 1

    # ── Generic phrase checks ───────────────────────────────────────────────
    all_text = " ".join([persona, hook] + [str(t) for t in themes])
    bad_phrases = check_generic_phrases(all_text)
    if bad_phrases:
        reasons.append(f"Generic phrases detected: {bad_phrases}")
        flags += 2  # weighted higher — generic = unusable

    # ── Specificity signal: does content mention company or role? ───────────
    company_words = [w for w in contact.get("company", "").lower().split() if len(w) > 3]
    title_words   = [w for w in contact.get("title", "").lower().split()
                     if w not in ("and", "the", "of", "at", "for", "&")]

    all_text_lower = all_text.lower()
    company_mentioned = any(w in all_text_lower for w in company_words)
    title_mentioned   = any(w in all_text_lower for w in title_words)

    if not company_mentioned and not title_mentioned:
        reasons.append("Output doesn't reference contact's company or role — too generic")
        flags += 2

    # ── LLM self-reported confidence ────────────────────────────────────────
    llm_confidence = parsed.get("confidence", "LOW")
    if llm_confidence == "LOW":
        reasons.append("LLM self-reported LOW confidence")
        flags += 3

    # ── Compute final confidence ────────────────────────────────────────────
    if flags == 0 and llm_confidence == "HIGH":
        final = "HIGH"
    elif flags <= 2:
        final = "MEDIUM"
    else:
        final = "LOW"

    return final, reasons


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def validate_persona(
    raw_llm_output: str,
    contact: dict,
) -> dict:
    """
    Full validation pipeline for a single LLM persona output.

    Args:
        raw_llm_output: Raw string returned by the LLM
        contact:        Original contact dict (for specificity checks)

    Returns:
        dict with keys:
          - persona_summary
          - context_hook
          - personalization_themes  (joined as string for CSV storage)
          - confidence_flag         ('HIGH' | 'MEDIUM' | 'LOW')
          - validation_notes        (pipe-separated list of issues, empty if clean)
    """
    result = {
        "persona_summary":         "",
        "context_hook":            "",
        "personalization_themes":  "",
        "confidence_flag":         "LOW",
        "validation_notes":        "",
    }

    # ── Step 1: Parse ──────────────────────────────────────────────────────
    parsed, parse_error = parse_llm_output(raw_llm_output)
    if not parsed:
        result["validation_notes"] = f"PARSE_ERROR: {parse_error}"
        log.warning(f"[{contact.get('name')}] Persona parse failed: {parse_error}")
        return result

    # ── Step 2: Structural validation ─────────────────────────────────────
    is_valid, struct_issues = validate_structure(parsed)
    if not is_valid:
        result["validation_notes"] = "STRUCT_ERROR: " + " | ".join(struct_issues)
        log.warning(f"[{contact.get('name')}] Structural issues: {struct_issues}")
        return result

    # ── Step 3: Semantic / specificity check ───────────────────────────────
    final_confidence, reasons = check_specificity(parsed, contact)

    # ── Step 4: Pack result ────────────────────────────────────────────────
    themes = parsed.get("personalization_themes", [])
    result["persona_summary"]        = parsed.get("persona_summary", "").strip()
    result["context_hook"]           = parsed.get("context_hook", "").strip()
    result["personalization_themes"] = " | ".join(str(t).strip() for t in themes)
    result["confidence_flag"]        = final_confidence
    result["validation_notes"]       = " | ".join(reasons) if reasons else ""

    if final_confidence == "LOW":
        log.warning(f"[{contact.get('name')}] LOW confidence: {reasons}")
    elif final_confidence == "MEDIUM":
        log.info(f"[{contact.get('name')}] MEDIUM confidence: {reasons}")
    else:
        log.info(f"[{contact.get('name')}] HIGH confidence ✅")

    return result


# ─────────────────────────────────────────────────────────────────────────────
# BATCH SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

def print_confidence_report(results: list[dict]):
    """Print a summary of confidence distribution across a batch."""
    from collections import Counter
    counts = Counter(r["confidence_flag"] for r in results)
    total  = len(results)

    print("\n" + "=" * 50)
    print("  PERSONA CONFIDENCE REPORT")
    print("=" * 50)
    for level in ("HIGH", "MEDIUM", "LOW"):
        n = counts.get(level, 0)
        bar = "█" * int(n / total * 30)
        print(f"  {level:<8} {n:>3} ({n/total*100:4.0f}%)  {bar}")

    low_contacts = [r for r in results if r["confidence_flag"] == "LOW"]
    if low_contacts:
        print(f"\n  ⚠️  {len(low_contacts)} contacts flagged for human review")
        print("  These will NOT be sent to outreach automatically.")
    print("=" * 50 + "\n")
