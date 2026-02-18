"""
persona_generation/persona_generator.py
=========================================
Orchestrates LLM persona generation for all enriched contacts.

Flow:
  1. Load enriched CSV
  2. For each contact (prioritised by ICP score):
       a. Select prompt variant (persona type)
       b. Call Claude via OpenRouter API
       c. Validate output (confidence_checker)
       d. Write result back to row
  3. Save final CSV to data/final/techsparks_master.csv
  4. Print confidence report

Rate limits (OpenRouter free tier):
  - ~20 req/min on free credits
  - We process high ICP first so if credits run out, we have the best contacts done

HOW TO RUN:
    export OPENROUTER_API_KEY=your_key_here
    python persona_generation/persona_generator.py

    # Dry run (uses pre-written sample personas, no API calls):
    python persona_generation/persona_generator.py --dry-run

    # Process only top N contacts by ICP score:
    python persona_generation/persona_generator.py --limit 20
"""

import os
import sys
import time
import json
import logging
import argparse
import requests
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import OPENROUTER_API_KEY, DATA_ENRICHED, DATA_FINAL
from persona_generation.prompt_templates import get_prompt, format_user_prompt, ACTIVE_VERSION
from persona_generation.confidence_checker import validate_persona, print_confidence_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("persona_generation/persona_generator.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# ── OpenRouter API settings ───────────────────────────────────────────────────
OPENROUTER_URL   = "https://openrouter.ai/api/v1/chat/completions"
MODEL            = "anthropic/claude-3-haiku"   # Fast + cheap on free tier
RATE_LIMIT_DELAY = 3                             # seconds between requests
MAX_RETRIES      = 3


# ─────────────────────────────────────────────────────────────────────────────
# API CLIENT
# ─────────────────────────────────────────────────────────────────────────────

def call_llm(system_prompt: str, user_prompt: str) -> str:
    """
    Call Claude via OpenRouter and return the raw text response.

    Args:
        system_prompt: Role/constraints for the LLM
        user_prompt:   Contact data + output format instructions

    Returns:
        Raw string response from the model
    """
    if not OPENROUTER_API_KEY:
        raise ValueError(
            "OPENROUTER_API_KEY not set. "
            "Export it: export OPENROUTER_API_KEY=your_key"
        )

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type":  "application/json",
        "HTTP-Referer":  "https://github.com/techsparks-gtm",  # required by OpenRouter
    }

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "temperature":  0.3,   # Low temp = more consistent, less hallucination
        "max_tokens":   600,
        "response_format": {"type": "json_object"},  # enforce JSON output
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            time.sleep(RATE_LIMIT_DELAY)
            resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=20)

            if resp.status_code == 200:
                data = resp.json()
                return data["choices"][0]["message"]["content"]

            elif resp.status_code == 429:
                wait = 30 * attempt
                log.warning(f"Rate limited — waiting {wait}s (attempt {attempt})")
                time.sleep(wait)

            else:
                log.error(f"API error {resp.status_code}: {resp.text[:300]}")
                if attempt == MAX_RETRIES:
                    return ""

        except requests.exceptions.RequestException as e:
            log.error(f"Request failed (attempt {attempt}): {e}")
            if attempt < MAX_RETRIES:
                time.sleep(10)

    return ""


# ─────────────────────────────────────────────────────────────────────────────
# DRY RUN: Pre-written sample personas for testing without API calls
# Covers all 3 persona variants (Fintech founder, VC, Government)
# ─────────────────────────────────────────────────────────────────────────────

DRY_RUN_PERSONAS = {
    # Variant A — Fintech / D2C / SaaS founder
    "default": json.dumps({
        "persona_summary": "As Founder & CEO, this executive owns both product strategy and commercial outcomes. At a bootstrapped fintech operating in a margin-sensitive category, they are acutely focused on pricing strategy, competitive positioning, and unit economics as they scale without external capital to absorb mistakes.",
        "context_hook": "Bootstrapped fintechs live and die by pricing discipline. Competitive benchmarking and real-time pricing intelligence directly impact their ability to acquire and retain customers without burning cash.",
        "personalization_themes": [
            "Maintaining competitive pricing edge without a large analytics team",
            "Using data to defend margins as larger funded competitors undercut on price",
            "Automating market intelligence that currently requires manual effort"
        ],
        "confidence": "HIGH"
    }),
    # Variant B — VC/PE investor
    "VC/PE": json.dumps({
        "persona_summary": "As a Managing Partner at a growth-stage VC, this investor sits on boards of 8–12 portfolio companies across fintech and SaaS. Their operational value-add often includes connecting portfolio founders with tools that improve commercial performance.",
        "context_hook": "Portfolio companies in competitive consumer categories frequently lack systematic pricing intelligence. A VC champion who surfaces this capability to their founders creates direct value for their fund's returns.",
        "personalization_themes": [
            "Portfolio value creation through better pricing and competitive benchmarking tools",
            "Early-stage portfolio companies need affordable data automation before they can hire analysts",
            "Warm intro pathway: VC introduces product to 5–10 relevant portfolio founders"
        ],
        "confidence": "HIGH"
    }),
    # Government — low confidence, minimal output
    "Government": json.dumps({
        "persona_summary": "Senior government official focused on technology policy and startup ecosystem development. Influences the regulatory framework within which Indian startups operate.",
        "context_hook": "Indirect relevance only — shapes the policy environment for data-driven businesses in India.",
        "personalization_themes": [
            "Policy and regulatory landscape for data businesses",
            "Startup ecosystem enablement role",
            "Awareness contact only — not a sales prospect"
        ],
        "confidence": "LOW"
    }),
}


def get_dry_run_persona(contact: dict) -> str:
    """Return a pre-written persona matching the contact's industry."""
    industry = contact.get("industry_vertical", "default")
    return DRY_RUN_PERSONAS.get(industry, DRY_RUN_PERSONAS["default"])


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────

def generate_personas(
    input_path:  str  = DATA_ENRICHED,
    output_path: str  = DATA_FINAL,
    dry_run:     bool = False,
    limit:       int  = None,
) -> pd.DataFrame:
    """
    Generate personas for all enriched contacts.

    Args:
        input_path:  Enriched CSV (Step 2 output)
        output_path: Master CSV with personas added (Step 3 output)
        dry_run:     Skip API calls, use pre-written personas
        limit:       Process only top N contacts by ICP score

    Returns:
        DataFrame with persona columns populated
    """
    log.info(f"Loading: {input_path}")
    df = pd.read_csv(input_path)

    # Process highest ICP first — if credits run out, best contacts are done
    df = df.sort_values("icp_score", ascending=False).reset_index(drop=True)

    if limit:
        df = df.head(limit)
        log.info(f"Processing top {limit} contacts by ICP score")

    log.info(f"Generating personas for {len(df)} contacts | "
             f"Model: {MODEL} | Version: {ACTIVE_VERSION} | "
             f"Dry run: {dry_run}")

    results      = []
    all_validated = []
    total        = len(df)

    for i, row in df.iterrows():
        contact = row.to_dict()
        log.info(f"[{i+1}/{total}] {contact['name']} @ {contact['company']} "
                 f"(ICP {contact['icp_score']}, {contact['industry_vertical']})")

        # ── Get prompt pair ────────────────────────────────────────────────
        system_prompt, user_template = get_prompt(contact)
        user_prompt = format_user_prompt(contact, user_template)

        # ── Call LLM or use dry-run sample ────────────────────────────────
        if dry_run:
            raw_output = get_dry_run_persona(contact)
        else:
            raw_output = call_llm(system_prompt, user_prompt)

        # ── Validate output ────────────────────────────────────────────────
        validated = validate_persona(raw_output, contact)
        all_validated.append(validated)

        # ── Merge into row ─────────────────────────────────────────────────
        contact.update(validated)
        results.append(contact)

        # ── Checkpoint every 25 rows ───────────────────────────────────────
        if (i + 1) % 25 == 0:
            checkpoint = output_path.replace(".csv", f"_checkpoint_{i+1}.csv")
            pd.DataFrame(results).to_csv(checkpoint, index=False)
            log.info(f"  💾 Checkpoint: {checkpoint}")

    # ── Save final output ──────────────────────────────────────────────────
    final_df = pd.DataFrame(results)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    final_df.to_csv(output_path, index=False)
    log.info(f"✅ Personas saved → {output_path}")

    # ── Print confidence report ────────────────────────────────────────────
    print_confidence_report(all_validated)

    # ── Print sample personas ──────────────────────────────────────────────
    _print_sample_personas(final_df)

    return final_df


def _print_sample_personas(df: pd.DataFrame):
    """Print 3 sample personas (one per confidence tier) to stdout."""
    print("\n" + "=" * 60)
    print("  SAMPLE PERSONAS")
    print("=" * 60)

    for level in ("HIGH", "MEDIUM", "LOW"):
        subset = df[df["confidence_flag"] == level]
        if subset.empty:
            continue
        row = subset.iloc[0]
        print(f"\n  [{level} CONFIDENCE] {row['name']} — {row['title']} @ {row['company']}")
        print(f"  ICP Score: {row['icp_score']} | Industry: {row['industry_vertical']}")
        print(f"\n  Persona Summary:")
        print(f"    {row['persona_summary']}")
        print(f"\n  Context Hook:")
        print(f"    {row['context_hook']}")
        print(f"\n  Personalization Themes:")
        for theme in str(row['personalization_themes']).split(" | "):
            print(f"    • {theme}")
        if row.get("validation_notes"):
            print(f"\n  ⚠️  Validation Notes: {row['validation_notes']}")
        print()

    print("=" * 60 + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate LLM personas for TechSparks contacts")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip API calls, use pre-written sample personas")
    parser.add_argument("--limit",   type=int, default=None,
                        help="Process only top N contacts by ICP score")
    parser.add_argument("--input",   default=DATA_ENRICHED, help="Input CSV")
    parser.add_argument("--output",  default=DATA_FINAL,    help="Output CSV")
    args = parser.parse_args()

    generate_personas(
        input_path=args.input,
        output_path=args.output,
        dry_run=args.dry_run,
        limit=args.limit,
    )
