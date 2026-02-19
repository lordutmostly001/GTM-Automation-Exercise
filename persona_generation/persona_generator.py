"""
persona_generation/persona_generator.py
=========================================
Orchestrates LLM persona generation for all enriched contacts.
Produces a single output file — no checkpoints.
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

OPENROUTER_URL   = "https://openrouter.ai/api/v1/chat/completions"
MODEL            = "anthropic/claude-3-haiku"
RATE_LIMIT_DELAY = 3
MAX_RETRIES      = 3


def call_llm(system_prompt: str, user_prompt: str) -> str:
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY not set.")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type":  "application/json",
        "HTTP-Referer":  "https://github.com/techsparks-gtm",
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "temperature":     0.3,
        "max_tokens":      600,
        "response_format": {"type": "json_object"},
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            time.sleep(RATE_LIMIT_DELAY)
            resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=20)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            elif resp.status_code == 429:
                wait = 30 * attempt
                log.warning(f"Rate limited — waiting {wait}s")
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


DRY_RUN_PERSONAS = {
    "default": json.dumps({
        "persona_summary": "As Founder & CEO, this executive owns both product strategy and commercial outcomes. At a bootstrapped fintech operating in a margin-sensitive category, they are acutely focused on pricing strategy, competitive positioning, and unit economics as they scale without external capital to absorb mistakes.",
        "context_hook": "Bootstrapped fintechs live and die by pricing discipline. Competitive benchmarking and real-time pricing intelligence directly impact their ability to acquire and retain customers without burning cash.",
        "personalization_themes": ["Maintaining competitive pricing edge without a large analytics team", "Using data to defend margins as larger funded competitors undercut on price", "Automating market intelligence that currently requires manual effort"],
        "confidence": "HIGH"
    }),
    "VC/PE": json.dumps({
        "persona_summary": "As a Managing Partner at a growth-stage VC, this investor sits on boards of 8-12 portfolio companies across fintech and SaaS. Their operational value-add often includes connecting portfolio founders with tools that improve commercial performance.",
        "context_hook": "Portfolio companies in competitive consumer categories frequently lack systematic pricing intelligence. A VC champion who surfaces this capability to their founders creates direct value for their fund returns.",
        "personalization_themes": ["Portfolio value creation through better pricing and competitive benchmarking tools", "Early-stage portfolio companies need affordable data automation before they can hire analysts", "Warm intro pathway: VC introduces product to 5-10 relevant portfolio founders"],
        "confidence": "HIGH"
    }),
    "Government": json.dumps({
        "persona_summary": "Senior government official focused on technology policy and startup ecosystem development. Influences the regulatory framework within which Indian startups operate.",
        "context_hook": "Indirect relevance only — shapes the policy environment for data-driven businesses in India.",
        "personalization_themes": ["Policy and regulatory landscape for data businesses", "Startup ecosystem enablement role", "Awareness contact only — not a sales prospect"],
        "confidence": "LOW"
    }),
}


def get_dry_run_persona(contact: dict) -> str:
    industry = contact.get("industry_vertical", "default")
    return DRY_RUN_PERSONAS.get(industry, DRY_RUN_PERSONAS["default"])


def generate_personas(
    input_path:  str  = DATA_ENRICHED,
    output_path: str  = DATA_FINAL,
    dry_run:     bool = False,
    limit:       int  = None,
) -> pd.DataFrame:

    log.info(f"Loading: {input_path}")
    df = pd.read_csv(input_path)
    df = df.sort_values("icp_score", ascending=False).reset_index(drop=True)

    if limit:
        df = df.head(limit)
        log.info(f"Processing top {limit} contacts by ICP score")

    log.info(f"Generating personas for {len(df)} contacts | Model: {MODEL} | Dry run: {dry_run}")

    results       = []
    all_validated = []
    total         = len(df)

    for i, row in df.iterrows():
        contact = row.to_dict()
        log.info(f"[{i+1}/{total}] {contact['name']} @ {contact['company']} "
                 f"(ICP {contact['icp_score']}, {contact['industry_vertical']})")

        system_prompt, user_template = get_prompt(contact)
        user_prompt = format_user_prompt(contact, user_template)

        raw_output = get_dry_run_persona(contact) if dry_run else call_llm(system_prompt, user_prompt)

        validated = validate_persona(raw_output, contact)
        all_validated.append(validated)
        contact.update(validated)
        results.append(contact)

    # Single output file — no checkpoints
    final_df = pd.DataFrame(results)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    final_df.to_csv(output_path, index=False)
    log.info(f"✅ Personas saved → {output_path}")

    print_confidence_report(all_validated)
    _print_sample_personas(final_df)
    return final_df


def _print_sample_personas(df: pd.DataFrame):
    print("\n" + "=" * 60)
    print("  SAMPLE PERSONAS")
    print("=" * 60)
    for level in ("HIGH", "MEDIUM", "LOW"):
        subset = df[df["confidence_flag"] == level]
        if subset.empty:
            continue
        row = subset.iloc[0]
        print(f"\n  [{level}] {row['name']} — {row['title']} @ {row['company']}")
        print(f"  ICP: {row['icp_score']} | Industry: {row['industry_vertical']}")
        print(f"  Persona: {row['persona_summary']}")
        print(f"  Hook: {row['context_hook']}")
        if row.get("validation_notes"):
            print(f"  Notes: {row['validation_notes']}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit",   type=int, default=None)
    parser.add_argument("--input",   default=DATA_ENRICHED)
    parser.add_argument("--output",  default=DATA_FINAL)
    args = parser.parse_args()

    generate_personas(
        input_path=args.input,
        output_path=args.output,
        dry_run=args.dry_run,
        limit=args.limit,
    )
