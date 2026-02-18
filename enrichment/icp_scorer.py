"""
enrichment/icp_scorer.py
=========================
Computes ICP (Ideal Customer Profile) scores for each contact.

Score = seniority_weight + industry_weight  (capped at 5)

This module is intentionally stateless — it takes a row dict and
returns a score. No I/O, no API calls, fully testable in isolation.
"""

import re
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import SENIORITY_WEIGHTS, INDUSTRY_WEIGHTS

# ── Keyword maps for inference ────────────────────────────────────────────────

SENIORITY_KEYWORD_MAP = {
    "C-Suite": [
        "founder", "co-founder", "ceo", "cto", "coo", "cfo", "cpo",
        "chief", "chairman", "managing director", "md &", "md,",
        "executive chairman", "president",
    ],
    "VP/Director": [
        "vp ", "vp,", "vice president", "director", "head of",
        "partner", "managing partner", "founding partner",
        "sherpa", "principal", "svp", "evp", "general partner",
        "investment director", "country head", "country director",
    ],
    "Manager/IC": [
        "manager", "lead", "engineer", "analyst",
        "associate", "consultant", "specialist",
    ],
}

INDUSTRY_KEYWORD_MAP = {
    "Fintech": [
        "zerodha", "razorpay", "groww", "phonePe", "open financial",
        "paytm", "cred", "lendgrid", "finstack", "insurancefirst",
        "wealthbridge", "payflow", "creditsense", "loantap", "finova",
        "razorx", "neobank", "simpl", "acko", "cashify", "ezetap",
        "policybazaar", "pine labs", "capital float", "zeta", "accesspay",
        "instamojo", "juspay",
    ],
    "D2C/Ecomm": [
        "mensa", "snapdeal", "nykaa", "boat", "plum", "bey bee",
        "snitch", "mamaearth", "aastey", "blissclub", "wow skin",
        "pilgrim", "moms co", "zivame", "monrow", "sirona", "epigamia",
        "true elements", "fynd", "firstcry", "meesho", "beato", "blippar",
        "sugar cosmetics", "freshmenu", "licious", "assiduus",
    ],
    "SaaS/B2B": [
        "inmobi", "freshworks", "zoho", "chargebee", "postman",
        "saasify", "stackr", "quickwork", "zomentum", "clientjoy",
        "sprinto", "rocketlane", "leadsquared", "demandbase", "haptik",
        "salesken", "moengage", "greyhound", "humanic", "harness",
        "browserstack", "unicommerce", "locus", "ventive", "helpshift",
        "salesforce", "aws", "infosys", "wipro", "accenture", "kpmg",
        "giggr",
    ],
    "VC/PE": [
        "elevation capital", "3one4", "prosus", "sequoia", "tiger",
        "blume", "accel", "lightspeed", "matrix", "antler", "omidyar",
        "nexus", "saif", "kalaari", "yournest", "ideaspring",
        "ventureintelligence", "stellaris", "chiratae", "inventus",
        "saama", "100x.vc", "angel network", "mumbai angels",
        "peak xv", "carlyle", "intel capital", "angellist",
        "advantedge", "prime venture", "gsf", "lead angels",
        "motwani", "js & associates",
    ],
    "DeepTech/AI": [
        "neysa", "nvidia", "microsoft", "isro", "sarvam",
        "mad street", "detect tech", "ather", "krutrim", "sqream",
        "mphasis", "ventive",
    ],
    "Edtech": [
        "upgrad", "byju", "unacademy", "eruditus", "classplus",
        "scaler", "next education", "imarticus", "hero vired",
        "lead school", "vymo", "udhyam", "physics wallah",
    ],
    "Mobility": [
        "ola", "rapido", "yulu", "blusmart", "zypp", "jetsetgo",
        "spinny", "park+", "letstransport", "dunzo",
    ],
    "Government": [
        "government of india", "competition commission",
        "g20", "nasscom", "ispirt", "ministry",
    ],
}


def infer_seniority(title: str) -> str:
    """
    Infer seniority tier from job title.
    Returns: 'C-Suite' | 'VP/Director' | 'Manager/IC'
    """
    t = title.lower()
    for tier, keywords in SENIORITY_KEYWORD_MAP.items():
        if any(kw in t for kw in keywords):
            return tier
    return "Manager/IC"


def infer_industry(company: str, title: str = "") -> str:
    """
    Infer industry vertical from company name and title text.
    Returns the best-matching industry label from INDUSTRY_KEYWORD_MAP.
    Falls back to 'SaaS/B2B' for unknown Indian startup ecosystem contacts.
    """
    text = (company + " " + title).lower()
    for industry, keywords in INDUSTRY_KEYWORD_MAP.items():
        if industry == "Other":
            continue
        if any(kw.lower() in text for kw in keywords):
            return industry
    return "SaaS/B2B"


def compute_icp_score(seniority: str, industry: str) -> int:
    """
    Compute ICP score 1–5.
    Score = seniority_weight + industry_weight, capped at 5.

    Context: product is pricing intelligence / data automation.
    High-value buyers = senior decision-makers at companies where
    pricing, assortment, or competitive data is operationally critical.
    """
    s = SENIORITY_WEIGHTS.get(seniority, 1)
    i = INDUSTRY_WEIGHTS.get(industry, 0)
    return min(5, max(1, s + i))


def score_row(row: dict) -> dict:
    """
    Takes a contact dict, infers and computes all scoring fields.
    Returns the row updated with seniority_tier, industry_vertical, icp_score.
    Does NOT mutate the original — returns a new dict.
    """
    row = dict(row)  # copy

    # Use existing values if already set (e.g., from Apollo enrichment)
    seniority = row.get("seniority_tier") or infer_seniority(row.get("title", ""))
    industry  = row.get("industry_vertical") or infer_industry(
        row.get("company", ""), row.get("title", "")
    )
    score = compute_icp_score(seniority, industry)

    row["seniority_tier"]     = seniority
    row["industry_vertical"]  = industry
    row["icp_score"]          = score

    return row


# ── CLI: re-score an existing CSV ─────────────────────────────────────────────

if __name__ == "__main__":
    import pandas as pd
    from config.settings import DATA_RAW, DATA_ENRICHED

    input_path  = sys.argv[1] if len(sys.argv) > 1 else DATA_RAW
    output_path = sys.argv[2] if len(sys.argv) > 2 else DATA_ENRICHED

    print(f"[icp_scorer] Reading: {input_path}")
    df = pd.read_csv(input_path)

    scored = df.apply(lambda r: pd.Series(score_row(r.to_dict())), axis=1)
    df["seniority_tier"]    = scored["seniority_tier"]
    df["industry_vertical"] = scored["industry_vertical"]
    df["icp_score"]         = scored["icp_score"]

    df.to_csv(output_path, index=False)
    print(f"[icp_scorer] Scored {len(df)} contacts → {output_path}")
    print(df["icp_score"].value_counts().sort_index(ascending=False))
