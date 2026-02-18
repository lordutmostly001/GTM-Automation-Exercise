"""
persona_generation/prompt_templates.py
=======================================
All LLM prompts used in the pipeline, versioned and centralized.

Design principles:
  - Every prompt explicitly constrains the LLM to use ONLY provided data
  - Outputs are structured (JSON) so they're machine-parseable
  - Prompts are versioned so we can A/B test and track what changed
  - System prompt sets the role; user prompt passes the contact data

Version history:
  v1.0 — Initial prompt (single persona blob)
  v1.1 — Split into 3 structured fields + added confidence field
  v1.2 — Added anti-hallucination constraints + JSON output enforcement
"""

# ─────────────────────────────────────────────────────────────────────────────
# PROMPT VERSION IN USE
# ─────────────────────────────────────────────────────────────────────────────
ACTIVE_VERSION = "v1.2"


# ─────────────────────────────────────────────────────────────────────────────
# v1.2 — PERSONA GENERATION PROMPT (PRODUCTION)
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT_V1_2 = """You are a B2B sales intelligence assistant helping a GTM team 
personalize outreach for attendees of TechSparks 2024, India's largest tech startup event.

Your job is to generate a short persona profile for each contact based ONLY on the 
structured data provided. 

STRICT RULES — violations will cause the output to be rejected:
1. Use ONLY the fields provided in the input JSON. Do not invent job history, 
   funding amounts, personal details, or facts not present in the input.
2. Do not use generic filler phrases like: "passionate about", "thought leader", 
   "driving innovation", "seasoned professional", "dynamic", "visionary", 
   "at the forefront", "in the tech space", "as a leader".
3. Output must be valid JSON — no markdown, no preamble, no explanation outside the JSON.
4. Keep all text fields concise: persona_summary ≤ 60 words, context_hook ≤ 50 words.
5. If the data is insufficient to generate a confident, specific output, set 
   confidence to "LOW" and keep the text minimal — do not pad with generic content.

The product context (do NOT mention the company name in any output):
- A YC-backed data intelligence platform
- Core value: pricing intelligence, competitive benchmarking, assortment insights, 
  and data automation for businesses that compete on price or product range
- Most relevant to: Fintech, D2C/Ecomm, SaaS/B2B companies; less relevant to VC/PE, Government
"""

USER_PROMPT_V1_2 = """Generate a persona profile for this contact.

INPUT DATA:
{contact_json}

OUTPUT FORMAT (valid JSON only, no other text):
{{
  "persona_summary": "<3 sentences max. Role archetype, what they're operationally responsible for, and their likely decision-making lens. Be specific to their title and industry.>",
  "context_hook": "<1-2 sentences. Why pricing intelligence OR competitive benchmarking OR data automation is specifically relevant to someone in their role at their type of company. Be direct, not generic.>",
  "personalization_themes": [
    "<Theme 1: a specific business pressure or goal relevant to their role>",
    "<Theme 2: a specific pain point or opportunity in their industry>",
    "<Theme 3: a relevant angle for a YC-backed data product intro>"
  ],
  "confidence": "<HIGH | MEDIUM | LOW — HIGH means all 3 fields are specific and grounded in the input data. LOW means data was insufficient for specificity.>"
}}"""


# ─────────────────────────────────────────────────────────────────────────────
# VARIANT PROMPTS — by persona type
# Used when the base prompt produces LOW confidence for certain industries
# ─────────────────────────────────────────────────────────────────────────────

# For VC/PE contacts — different angle (portfolio intelligence vs. own ops)
SYSTEM_PROMPT_VC = """You are a B2B sales intelligence assistant.
Generate a persona profile for a VC/PE investor attending TechSparks 2024.

STRICT RULES:
1. Use ONLY the fields provided. Do not invent portfolio companies or investment history.
2. Avoid generic phrases. Be specific to the investor's stage focus and firm type.
3. Output valid JSON only.
4. The product angle for investors: portfolio companies need pricing and competitive 
   intelligence — the VC can become a champion who introduces the product to portfolio founders.
"""

USER_PROMPT_VC = """Generate a persona profile for this investor contact.

INPUT DATA:
{contact_json}

OUTPUT FORMAT (valid JSON only):
{{
  "persona_summary": "<Their role at the firm, typical stage/sector focus implied by firm name, and how they interact with portfolio companies.>",
  "context_hook": "<Why their portfolio companies would benefit from pricing intelligence or data automation — and why the investor might champion this intro.>",
  "personalization_themes": [
    "<Portfolio value creation angle>",
    "<Stage-specific pain: early-stage cos need pricing benchmarks to fundraise>",
    "<Positioning: offer a warm intro to relevant portfolio founders>"
  ],
  "confidence": "<HIGH | MEDIUM | LOW>"
}}"""


# For Government/Policy contacts — very low ICP, minimal outreach
SYSTEM_PROMPT_GOV = """You are a B2B sales intelligence assistant.
This contact works in government or policy. They are low priority for direct outreach.
Generate a minimal, neutral persona. Do not fabricate any policy positions or affiliations.
Output valid JSON only.
"""

USER_PROMPT_GOV = """Generate a minimal persona for this government/policy contact.

INPUT DATA:
{contact_json}

OUTPUT FORMAT (valid JSON only):
{{
  "persona_summary": "<Their official role and likely policy focus area based on their title.>",
  "context_hook": "<One sentence on indirect relevance — e.g., they influence the regulatory environment for startups.>",
  "personalization_themes": [
    "<Policy/regulatory angle only — no product pitch>",
    "<Ecosystem building angle>",
    "<Awareness only — not a sales contact>"
  ],
  "confidence": "LOW"
}}"""


# ─────────────────────────────────────────────────────────────────────────────
# PROMPT SELECTOR — picks the right system+user prompt pair per contact
# ─────────────────────────────────────────────────────────────────────────────

def get_prompt(contact: dict) -> tuple[str, str]:
    """
    Select the appropriate system + user prompt pair based on contact's industry.

    Args:
        contact: dict with at minimum 'industry_vertical' key

    Returns:
        (system_prompt, user_prompt) tuple
    """
    industry = contact.get("industry_vertical", "")

    if industry == "VC/PE":
        return SYSTEM_PROMPT_VC, USER_PROMPT_VC
    elif industry == "Government":
        return SYSTEM_PROMPT_GOV, USER_PROMPT_GOV
    else:
        return SYSTEM_PROMPT_V1_2, USER_PROMPT_V1_2


def format_user_prompt(contact: dict, user_prompt_template: str) -> str:
    """
    Inject contact data into the user prompt template.
    Only passes fields relevant to persona generation — strips tracking/status fields.

    Args:
        contact:               Full contact dict
        user_prompt_template:  Template string with {contact_json} placeholder

    Returns:
        Formatted prompt string ready to send to LLM
    """
    import json

    # Only pass fields the LLM should reason about
    # Deliberately exclude: id, source, outreach_status, in_sequence, assigned_to
    ALLOWED_FIELDS = [
        "name", "title", "company",
        "seniority_tier", "industry_vertical", "icp_score",
        "company_size", "funding_stage",
    ]

    filtered = {k: v for k, v in contact.items()
                if k in ALLOWED_FIELDS and v and str(v).strip() not in ["", "nan"]}

    return user_prompt_template.format(contact_json=json.dumps(filtered, indent=2))


# ─────────────────────────────────────────────────────────────────────────────
# QUICK SANITY CHECK
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sample = {
        "name": "Nithin Kamath",
        "title": "Founder & CEO",
        "company": "Zerodha & Rainmatter",
        "seniority_tier": "C-Suite",
        "industry_vertical": "Fintech",
        "icp_score": 5,
        "company_size": "1001–5000",
        "funding_stage": "bootstrapped",
    }

    system, user_template = get_prompt(sample)
    user = format_user_prompt(sample, user_template)

    print("=== SYSTEM PROMPT ===")
    print(system)
    print("\n=== USER PROMPT ===")
    print(user)
    print(f"\nActive prompt version: {ACTIVE_VERSION}")
