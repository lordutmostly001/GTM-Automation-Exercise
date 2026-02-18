"""
config/settings.py
==================
Central configuration for the TechSparks GTM Automation pipeline.
All API keys are loaded from environment variables — never hardcode credentials.

Usage:
    from config.settings import APOLLO_API_KEY, ICP_THRESHOLDS
"""

import os

# ── API Keys (set these in your .env or shell before running) ─────────────────
APOLLO_API_KEY        = os.getenv("APOLLO_API_KEY", "")           # apollo.io
OPENROUTER_API_KEY    = os.getenv("OPENROUTER_API_KEY", "")       # LLM calls
PHANTOMBUSTER_API_KEY = os.getenv("PHANTOMBUSTER_API_KEY", "")    # LinkedIn enrichment
INSTANTLY_API_KEY     = os.getenv("INSTANTLY_API_KEY", "")        # Email sending

# ── File Paths ────────────────────────────────────────────────────────────────
DATA_RAW       = "data/raw/techsparks_contacts_200.csv"
DATA_ENRICHED  = "data/enriched/techsparks_enriched.csv"
DATA_FINAL     = "data/final/techsparks_master.csv"

# ── ICP Scoring Thresholds ────────────────────────────────────────────────────
ICP_THRESHOLDS = {
    "high":   5,     # Score 5   → Priority outreach, senior sender
    "medium": 4,     # Score 4   → Standard AE outreach
    "low":    3,     # Score 3   → SDR outreach
    "skip":   2,     # Score ≤ 2 → Hold, don't reach out
}

# ── Seniority → ICP Weight ────────────────────────────────────────────────────
SENIORITY_WEIGHTS = {
    "C-Suite":     3,
    "VP/Director": 2,
    "Manager/IC":  1,
}

# ── Industry → ICP Weight ─────────────────────────────────────────────────────
# Context: product is pricing intelligence / data automation / competitive benchmarking
INDUSTRY_WEIGHTS = {
    "Fintech":      2,   # High: pricing & margin pressure, competitive benchmarking
    "D2C/Ecomm":    2,   # High: assortment & price intelligence is core ops
    "SaaS/B2B":     2,   # High: competitive intel for sales & pricing strategy
    "VC/PE":        1,   # Medium: portfolio signal intelligence
    "DeepTech/AI":  1,   # Medium: data automation is their world
    "Edtech":       1,   # Medium: pricing strategy matters at scale
    "Mobility":     1,   # Medium: dynamic pricing is relevant
    "Government":   0,   # Low: not a buyer persona
    "Other":        0,
}

# ── Lead Routing Rules ────────────────────────────────────────────────────────
ROUTING_RULES = {
    "C-Suite":     {"owner_role": "Senior AE",  "sender_level": "Leadership"},
    "VP/Director": {"owner_role": "AE",          "sender_level": "AE"},
    "Manager/IC":  {"owner_role": "SDR",          "sender_level": "SDR"},
}

# ── Confidence Flag Thresholds (for LLM persona output) ──────────────────────
CONFIDENCE = {
    "high_flag_keywords": [           # If persona contains these → flag LOW confidence
        "as a leader", "in the tech space", "passionate about",
        "driving innovation", "thought leader", "seasoned professional",
        "dynamic", "visionary", "at the forefront",
    ],
    "min_persona_length": 80,         # Persona summary must be > 80 chars
    "min_hook_length": 60,            # Context hook must be > 60 chars
}

# ── Apollo Enrichment Settings ────────────────────────────────────────────────
APOLLO_SETTINGS = {
    "base_url":        "https://api.apollo.io/v1",
    "rate_limit_rpm":  10,             # Free tier: ~10 req/min
    "max_retries":     3,
    "retry_delay_s":   6,
    "fields_wanted": [
        "linkedin_url", "email", "organization.estimated_num_employees",
        "organization.funding_stage", "organization.industry",
        "seniority", "departments",
    ],
}

# ── Deduplication Settings ────────────────────────────────────────────────────
DEDUP_SETTINGS = {
    "fuzzy_threshold": 85,            # Levenshtein similarity % to flag as duplicate
    "merge_strategy":  "keep_first",  # keep_first | keep_highest_icp
}
