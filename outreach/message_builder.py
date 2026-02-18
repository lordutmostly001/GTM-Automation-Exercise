"""
outreach/message_builder.py
=============================
Merges persona data into outreach templates to produce 
personalized, send-ready messages for each contact.

Each contact gets 3 messages built:
  1. pre_event_linkedin  — connection request note
  2. during_event_dm     — LinkedIn DM after connection accepted
  3. post_event_email    — email body + subject line

Output: data/final/techsparks_outreach_ready.csv
  One row per contact, with all 3 messages as columns.
  Only contacts that pass all readiness gates are included.

HOW TO RUN:
    python outreach/message_builder.py
    python outreach/message_builder.py --limit 20   # preview top 20
"""

import os
import re
import sys
import logging
import argparse
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import DATA_FINAL, ROUTING_RULES

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

OUTPUT_PATH = "data/final/techsparks_outreach_ready.csv"


# ─────────────────────────────────────────────────────────────────────────────
# TEMPLATE DEFINITIONS
# Inline versions of the .md templates — used for programmatic substitution
# ─────────────────────────────────────────────────────────────────────────────

# ── Pre-event LinkedIn connection note (300 char limit) ───────────────────────

LI_CONNECT_A = (  # Fintech / D2C / SaaS founders
    "Hi {first_name}, spotted you on the TechSparks speaker list — your work "
    "at {their_company} on {personalization_1} caught my attention. "
    "Would love to connect ahead of the event. — {sender_name}"
)
LI_CONNECT_B = (  # VC / PE investors
    "Hi {first_name}, coming across your name ahead of TechSparks — "
    "founders I speak with are increasingly asking about {personalization_1}. "
    "Keen to connect and exchange notes. — {sender_name}"
)
LI_CONNECT_C = (  # VP / Director
    "Hi {first_name}, attending TechSparks next week and noticed your "
    "background at {their_company}. Working on problems around "
    "{personalization_1} — would love to connect. — {sender_name}"
)

# ── During-event LinkedIn DM ──────────────────────────────────────────────────

DM_A = """Hey {first_name},

Great connecting — your work at {their_company} is interesting, particularly around {personalization_1}.

{context_hook}

Not pitching anything — just thought it was directly relevant to what you're navigating. Happy to share what we're seeing across similar companies if useful.

{sender_name}
{sender_title}"""

DM_B = """Hey {first_name},

Appreciated connecting. Your firm's portfolio is interesting — particularly given how many companies are competing in price-sensitive categories right now.

{context_hook}

Worth a 20-min call to share what we're seeing across the ecosystem? Might be useful context for a couple of your portfolio founders specifically.

{sender_name}
{sender_title}"""

DM_C = """Hey {first_name},

Good to connect at TechSparks. Quick question — is {personalization_1} something your team is actively working through right now? We've been talking to a few people here with the same challenge.

{sender_name}"""

# ── Post-event email ──────────────────────────────────────────────────────────

EMAIL_SUBJECT_A = "Something relevant from TechSparks week — {first_name}"
EMAIL_SUBJECT_B = "Post-TechSparks — one thing worth passing to your portfolio"
EMAIL_SUBJECT_C = "Following up from TechSparks — {first_name}"

EMAIL_BODY_A = """Hi {first_name},

Hope the TechSparks energy has carried into this week.

I've been thinking about something relevant to {their_company} — {personalization_1}. It's a pattern we keep seeing with founders at your stage: the commercial intelligence work that should be informing pricing and competitive positioning is either delayed, manual, or not happening at the frequency needed.

{context_hook}

The companies getting ahead of this are using automated data pipelines to do in real-time what used to take an analyst a week — monitoring competitor pricing, tracking assortment gaps, benchmarking before board reviews.

If any of this resonates, I can introduce you to a YC-backed company that specializes in exactly this. They work with several Indian founders in your category and the conversation is worth 20 minutes.

Worth a quick intro?

{sender_name}
{sender_title}
{sender_email}"""

EMAIL_BODY_B = """Hi {first_name},

Good week at TechSparks. Wanted to follow up on something worth sharing with your portfolio.

{context_hook}

Several of your portfolio companies are likely navigating this right now — particularly the ones competing on price in consumer categories. {personalization_1}.

I know a YC-backed company that's built specifically for this: pricing intelligence, competitive benchmarking, and data automation for growth-stage companies. They've worked with founders across several top Indian VC portfolios.

If it's worth 15 minutes for a portfolio intro, I'm happy to make the connection.

{sender_name}
{sender_title}
{sender_email}"""

EMAIL_BODY_C = """Hi {first_name},

Quick follow-up from TechSparks last week.

{context_hook} — wanted to share something relevant around {personalization_1}.

There's a YC-backed company I'd be happy to introduce you to if this is on your radar. They work with teams your size on exactly this problem.

Let me know if useful.

{sender_name}"""


# ─────────────────────────────────────────────────────────────────────────────
# VARIANT SELECTOR
# ─────────────────────────────────────────────────────────────────────────────

def select_variant(contact: dict) -> str:
    """
    Determine which message variant (A/B/C) to use.
      A — Fintech, D2C/Ecomm, SaaS/B2B founders/C-Suite
      B — VC/PE (any seniority)
      C — VP/Director or Manager/IC in any industry
    """
    industry  = contact.get("industry_vertical", "")
    seniority = contact.get("seniority_tier", "")

    if industry == "VC/PE":
        return "B"
    elif seniority == "C-Suite" and industry in ("Fintech","D2C/Ecomm","SaaS/B2B","DeepTech/AI","Edtech","Mobility"):
        return "A"
    else:
        return "C"


# ─────────────────────────────────────────────────────────────────────────────
# READINESS GATES
# ─────────────────────────────────────────────────────────────────────────────

def is_ready_for_linkedin(contact: dict) -> tuple[bool, str]:
    """Check if contact is ready for LinkedIn outreach."""
    if not str(contact.get("linkedin_url","")).strip():
        return False, "no_linkedin_url"
    if contact.get("confidence_flag") == "LOW":
        return False, "low_confidence_persona"
    if str(contact.get("in_sequence","")).upper() == "TRUE":
        return False, "already_in_sequence"
    if contact.get("outreach_status","pending") not in ("pending",""):
        return False, f"status_{contact.get('outreach_status')}"
    return True, ""


def is_ready_for_email(contact: dict) -> tuple[bool, str]:
    """Check if contact is ready for email outreach."""
    if not str(contact.get("email","")).strip():
        return False, "no_email"
    if contact.get("icp_score", 0) < 3:
        return False, "icp_too_low"
    if contact.get("confidence_flag") == "LOW":
        return False, "low_confidence_persona"
    if str(contact.get("in_sequence","")).upper() == "TRUE":
        return False, "already_in_sequence"
    if contact.get("outreach_status","pending") not in ("pending",""):
        return False, f"status_{contact.get('outreach_status')}"
    return True, ""


# ─────────────────────────────────────────────────────────────────────────────
# VARIABLE EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────

SENDER = {
    "Leadership": {"name": "Rohan Mehta",   "title": "VP of Partnerships",     "email": "rohan@company.co"},
    "AE":         {"name": "Sneha Kapoor",  "title": "Account Executive",       "email": "sneha@company.co"},
    "SDR":        {"name": "Arjun Sharma",  "title": "Sales Development Rep",   "email": "arjun@company.co"},
}


def extract_variables(contact: dict) -> dict:
    """
    Extract and clean all template variables from a contact row.
    Returns a flat dict of substitution values.
    """
    # First name — handle "Dr." and multi-word names
    full_name  = str(contact.get("name",""))
    first_name = re.sub(r"^(Dr\.?|Mr\.?|Mrs\.?|Ms\.?|Prof\.?|Shri\.?)\s+", "", full_name, flags=re.IGNORECASE)
    first_name = first_name.split()[0]

    # Themes — stored as pipe-separated string
    themes_raw = str(contact.get("personalization_themes",""))
    themes     = [t.strip() for t in themes_raw.split("|") if t.strip()]
    p1 = themes[0].lower() if len(themes) > 0 else "data-driven decision making"
    p2 = themes[1].lower() if len(themes) > 1 else "competitive intelligence"

    # Sender based on routing
    sender_level = ROUTING_RULES.get(contact.get("seniority_tier","Manager/IC"), {}).get("sender_level","SDR")
    sender       = SENDER.get(sender_level, SENDER["SDR"])

    return {
        "first_name":        first_name,
        "their_company":     contact.get("company", "your company"),
        "personalization_1": p1,
        "personalization_2": p2,
        "context_hook":      str(contact.get("context_hook","")).strip(),
        "session_topic":     f"{contact.get('industry_vertical','')} strategy and scaling",
        "sender_name":       sender["name"],
        "sender_title":      sender["title"],
        "sender_email":      sender["email"],
    }


def safe_format(template: str, variables: dict) -> str:
    """Format template, replacing any missing variables with a safe fallback."""
    try:
        return template.format(**variables)
    except KeyError as e:
        log.warning(f"Missing template variable: {e} — using fallback")
        # Fill missing keys with empty string and retry
        from string import Formatter
        keys = [f[1] for f in Formatter().parse(template) if f[1]]
        safe_vars = {k: variables.get(k, "") for k in keys}
        return template.format(**safe_vars)


# ─────────────────────────────────────────────────────────────────────────────
# MESSAGE BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_messages(contact: dict) -> dict:
    """
    Build all 3 outreach messages for a single contact.

    Returns:
        dict with keys: variant, li_connect, dm, email_subject, email_body,
                        li_ready, email_ready, li_skip_reason, email_skip_reason
    """
    variant   = select_variant(contact)
    variables = extract_variables(contact)

    li_ok,    li_reason    = is_ready_for_linkedin(contact)
    email_ok, email_reason = is_ready_for_email(contact)

    # ── LinkedIn connection note ───────────────────────────────────────────
    li_template = {"A": LI_CONNECT_A, "B": LI_CONNECT_B, "C": LI_CONNECT_C}[variant]
    li_connect  = safe_format(li_template, variables) if li_ok else ""

    # Enforce 300 char limit
    if li_connect and len(li_connect) > 300:
        li_connect = li_connect[:297] + "..."

    # ── During-event DM ───────────────────────────────────────────────────
    dm_template = {"A": DM_A, "B": DM_B, "C": DM_C}[variant]
    dm          = safe_format(dm_template, variables) if li_ok else ""

    # ── Post-event email ──────────────────────────────────────────────────
    subject_template = {"A": EMAIL_SUBJECT_A, "B": EMAIL_SUBJECT_B, "C": EMAIL_SUBJECT_C}[variant]
    body_template    = {"A": EMAIL_BODY_A,    "B": EMAIL_BODY_B,    "C": EMAIL_BODY_C}[variant]
    email_subject    = safe_format(subject_template, variables) if email_ok else ""
    email_body       = safe_format(body_template,    variables) if email_ok else ""

    return {
        "variant":           variant,
        "li_connect_msg":    li_connect,
        "during_event_dm":   dm,
        "email_subject":     email_subject,
        "email_body":        email_body,
        "li_ready":          "YES" if li_ok    else "NO",
        "email_ready":       "YES" if email_ok else "NO",
        "li_skip_reason":    li_reason,
        "email_skip_reason": email_reason,
    }


# ─────────────────────────────────────────────────────────────────────────────
# ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────

def build_all_messages(
    input_path:  str = DATA_FINAL,
    output_path: str = OUTPUT_PATH,
    limit:       int = None,
) -> pd.DataFrame:

    log.info(f"Loading: {input_path}")
    df = pd.read_csv(input_path).sort_values("icp_score", ascending=False)

    if limit:
        df = df.head(limit)

    results = []
    for _, row in df.iterrows():
        contact  = row.to_dict()
        messages = build_messages(contact)
        results.append({**contact, **messages})

    out_df = pd.DataFrame(results)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    out_df.to_csv(output_path, index=False)
    log.info(f"✅ Outreach-ready contacts saved → {output_path}")

    _print_summary(out_df)
    return out_df


def _print_summary(df: pd.DataFrame):
    total     = len(df)
    li_ready  = (df["li_ready"]    == "YES").sum()
    em_ready  = (df["email_ready"] == "YES").sum()
    both      = ((df["li_ready"] == "YES") & (df["email_ready"] == "YES")).sum()

    print(f"\n{'='*55}")
    print(f"  OUTREACH READINESS SUMMARY")
    print(f"{'='*55}")
    print(f"  Total contacts       : {total}")
    print(f"  LinkedIn ready       : {li_ready}  ({li_ready/total*100:.0f}%)")
    print(f"  Email ready          : {em_ready}  ({em_ready/total*100:.0f}%)")
    print(f"  Both channels ready  : {both}  ({both/total*100:.0f}%)")
    print(f"\n  Variant distribution:")
    print(df["variant"].value_counts().to_string())
    print(f"\n  LinkedIn skip reasons:")
    print(df[df["li_skip_reason"]!=""]["li_skip_reason"].value_counts().to_string())
    print(f"\n  Email skip reasons:")
    print(df[df["email_skip_reason"]!=""]["email_skip_reason"].value_counts().to_string())
    print(f"{'='*55}\n")

    # Print one sample message per variant
    for v in ("A","B","C"):
        sample = df[(df["variant"]==v) & (df["li_ready"]=="YES")]
        if sample.empty: continue
        row = sample.iloc[0]
        print(f"  SAMPLE VARIANT {v}: {row['name']} @ {row['company']}")
        print(f"  [{row['seniority_tier']} | {row['industry_vertical']} | ICP {row['icp_score']}]")
        print(f"\n  → LinkedIn Connect:")
        print(f"    {row['li_connect_msg']}")
        print(f"\n  → Email Subject: {row['email_subject']}")
        print(f"  → Email Body (first 200 chars):")
        print(f"    {str(row['email_body'])[:200]}...")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",  default=DATA_FINAL)
    parser.add_argument("--output", default=OUTPUT_PATH)
    parser.add_argument("--limit",  type=int, default=None)
    args = parser.parse_args()

    build_all_messages(args.input, args.output, args.limit)
