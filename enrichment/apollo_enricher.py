"""
enrichment/apollo_enricher.py
==============================
Enriches contacts via Apollo.io's People Match API (free tier).

For each contact, Apollo is queried with name + company to return:
  - LinkedIn URL
  - Verified email address
  - Company size (headcount band)
  - Funding stage
  - Seniority (Apollo's own classification — used to validate our inference)
  - Department

Free tier limits:
  - 50 email exports / month
  - 600 people match calls / hour
  → Strategy: prioritise ICP score ≥ 4 for email export; use match for all others

HOW TO RUN:
    export APOLLO_API_KEY=your_key_here
    python enrichment/apollo_enricher.py

OUTPUTS:
    data/enriched/techsparks_enriched.csv
"""

import os
import sys
import time
import json
import logging
import requests
import pandas as pd
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import APOLLO_API_KEY, APOLLO_SETTINGS, DATA_RAW, DATA_ENRICHED
from enrichment.icp_scorer import score_row

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("enrichment/apollo_enricher.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


# ── Apollo API client ─────────────────────────────────────────────────────────

class ApolloClient:
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError(
                "APOLLO_API_KEY is not set. "
                "Export it: export APOLLO_API_KEY=your_key"
            )
        self.api_key  = api_key
        self.base_url = APOLLO_SETTINGS["base_url"]
        self.headers  = {"Content-Type": "application/json", "Cache-Control": "no-cache"}
        self._request_count = 0

    def _rate_limit(self):
        """Respect Apollo free tier: 10 req/min → sleep 6s between calls."""
        self._request_count += 1
        if self._request_count % APOLLO_SETTINGS["rate_limit_rpm"] == 0:
            log.info(f"Rate limit pause after {self._request_count} requests...")
            time.sleep(60)  # full minute cooldown every 10 requests
        else:
            time.sleep(APOLLO_SETTINGS["retry_delay_s"])

    def people_match(self, name: str, company: str, export_email: bool = False) -> dict:
        """
        Call Apollo's /people/match endpoint.

        Args:
            name:         Full name of the contact
            company:      Company name
            export_email: Whether to consume an email export credit (costly on free tier)

        Returns:
            dict with enriched fields, or empty dict on failure
        """
        payload = {
            "api_key":      self.api_key,
            "name":         name,
            "organization_name": company,
            "reveal_personal_emails": export_email,
        }

        for attempt in range(1, APOLLO_SETTINGS["max_retries"] + 1):
            try:
                self._rate_limit()
                resp = requests.post(
                    f"{self.base_url}/people/match",
                    json=payload,
                    headers=self.headers,
                    timeout=10,
                )

                if resp.status_code == 200:
                    data = resp.json()
                    person = data.get("person", {})
                    return self._parse_person(person, export_email)

                elif resp.status_code == 422:
                    log.warning(f"[{name}] No match found in Apollo (422)")
                    return {}

                elif resp.status_code == 429:
                    wait = 60 * attempt
                    log.warning(f"[{name}] Rate limited (429) — waiting {wait}s")
                    time.sleep(wait)

                else:
                    log.error(f"[{name}] Apollo error {resp.status_code}: {resp.text[:200]}")
                    return {}

            except requests.exceptions.RequestException as e:
                log.error(f"[{name}] Request failed (attempt {attempt}): {e}")
                if attempt < APOLLO_SETTINGS["max_retries"]:
                    time.sleep(10 * attempt)

        return {}

    def _parse_person(self, person: dict, include_email: bool) -> dict:
        """Extract only the fields we care about from Apollo's person object."""
        if not person:
            return {}

        org = person.get("organization", {}) or {}

        result = {
            "linkedin_url":   person.get("linkedin_url", ""),
            "company_size":   self._parse_headcount(org.get("estimated_num_employees")),
            "funding_stage":  org.get("latest_funding_stage", ""),
            "apollo_seniority": person.get("seniority", ""),
            "apollo_dept":    ", ".join(person.get("departments", []) or []),
        }

        if include_email:
            email = (
                person.get("email")
                or (person.get("personal_emails") or [None])[0]
            )
            result["email"] = email or ""

        return result

    @staticmethod
    def _parse_headcount(num) -> str:
        """Convert raw headcount number to a band string."""
        if not num:
            return ""
        try:
            n = int(num)
            if n < 10:      return "1–10"
            elif n < 50:    return "11–50"
            elif n < 200:   return "51–200"
            elif n < 500:   return "201–500"
            elif n < 1000:  return "501–1000"
            elif n < 5000:  return "1001–5000"
            else:           return "5000+"
        except (ValueError, TypeError):
            return str(num)


# ── Enrichment orchestrator ───────────────────────────────────────────────────

def enrich_contacts(
    input_path:  str = DATA_RAW,
    output_path: str = DATA_ENRICHED,
    dry_run:     bool = False,
    limit:       int = None,
) -> pd.DataFrame:
    """
    Main enrichment function.

    Args:
        input_path:  Path to raw CSV (Step 1 output)
        output_path: Where to write enriched CSV
        dry_run:     If True, skips API calls and returns mock enriched data
        limit:       Process only first N rows (useful for testing)

    Returns:
        Enriched DataFrame
    """
    log.info(f"Loading contacts from: {input_path}")
    df = pd.read_csv(input_path)

    if limit:
        df = df.head(limit)
        log.info(f"Limiting to {limit} contacts for this run")

    # ── Decide which contacts get email export credits ────────────────────────
    # Only ICP score ≥ 4 consume email credits (free tier: 50/month)
    df = df.copy()
    df["export_email"] = df["icp_score"].apply(lambda s: s >= 4)

    email_export_count = df["export_email"].sum()
    log.info(f"Contacts queued: {len(df)} total | {email_export_count} email exports")

    if email_export_count > 50:
        log.warning(
            f"⚠️  {email_export_count} email exports requested but free tier allows 50/month. "
            "Reducing to top 50 by ICP score."
        )
        # Only top 50 by ICP score get email export
        top50_ids = df.nlargest(50, "icp_score").index
        df["export_email"] = False
        df.loc[top50_ids, "export_email"] = True

    if dry_run:
        log.info("DRY RUN mode — skipping API calls, using mock enrichment data")
        df = _mock_enrich(df)
    else:
        client = ApolloClient(APOLLO_API_KEY)
        df = _run_enrichment(df, client)

    # Re-score with any updated fields from Apollo
    log.info("Re-scoring ICP after enrichment...")
    df = df.apply(lambda r: pd.Series(score_row(r.to_dict())), axis=1)

    # Save checkpoint
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False)
    log.info(f"✅ Enriched {len(df)} contacts → {output_path}")

    _print_summary(df)
    return df


def _run_enrichment(df: pd.DataFrame, client: ApolloClient) -> pd.DataFrame:
    """Run Apollo enrichment row by row with progress logging."""
    enriched_rows = []
    total = len(df)

    for i, row in df.iterrows():
        log.info(f"[{i+1}/{total}] Enriching: {row['name']} @ {row['company']}")

        result = client.people_match(
            name=row["name"],
            company=row["company"],
            export_email=row.get("export_email", False),
        )

        # Merge enrichment results into the row
        updated = row.to_dict()
        if result:
            for field, value in result.items():
                # Don't overwrite existing non-empty values from Step 1
                if not updated.get(field):
                    updated[field] = value
            updated["enrichment_status"] = "enriched"
        else:
            updated["enrichment_status"] = "not_found"
            log.warning(f"  → No Apollo match for {row['name']} @ {row['company']}")

        enriched_rows.append(updated)

        # Auto-checkpoint every 25 rows
        if (i + 1) % 25 == 0:
            checkpoint_path = DATA_ENRICHED.replace(".csv", f"_checkpoint_{i+1}.csv")
            pd.DataFrame(enriched_rows).to_csv(checkpoint_path, index=False)
            log.info(f"  💾 Checkpoint saved: {checkpoint_path}")

    return pd.DataFrame(enriched_rows)


def _mock_enrich(df: pd.DataFrame) -> pd.DataFrame:
    """
    Mock enrichment for dry runs and testing.
    Simulates realistic Apollo response rates:
      - ~70% LinkedIn URL found
      - ~50% email found (matches our ICP ≥ 4 export rate)
      - ~85% company size found
    """
    import random
    random.seed(42)

    company_sizes  = ["11–50", "51–200", "201–500", "501–1000", "1001–5000", "5000+"]
    funding_stages = ["seed", "series_a", "series_b", "series_c", "public", ""]

    rows = []
    for _, row in df.iterrows():
        r = row.to_dict()
        found = random.random()

        if found > 0.30:  # 70% match rate
            # LinkedIn URL
            slug = row["name"].lower().replace(" ", "-").replace(".", "")
            r["linkedin_url"]    = f"https://www.linkedin.com/in/{slug}/"
            r["company_size"]    = random.choice(company_sizes)
            r["funding_stage"]   = random.choice(funding_stages)
            r["enrichment_status"] = "enriched"

            # Email only for high-ICP contacts
            if row.get("export_email"):
                first = row["name"].split()[0].lower()
                last  = row["name"].split()[-1].lower()
                domain = row["company"].lower().split()[0].replace("&", "").replace(",", "") + ".com"
                r["email"] = f"{first}.{last}@{domain}"

        else:
            r["enrichment_status"] = "not_found"

        rows.append(r)

    return pd.DataFrame(rows)


def _print_summary(df: pd.DataFrame):
    """Print enrichment quality summary to stdout."""
    total     = len(df)
    enriched  = (df.get("enrichment_status", pd.Series()) == "enriched").sum()
    has_email = df["email"].notna().apply(lambda x: bool(str(x).strip() and x != "nan")).sum()
    has_li    = df["linkedin_url"].notna().apply(lambda x: bool(str(x).strip() and x != "nan")).sum()

    print("\n" + "=" * 50)
    print("  ENRICHMENT SUMMARY")
    print("=" * 50)
    print(f"  Total contacts     : {total}")
    print(f"  Apollo matches     : {enriched} ({enriched/total*100:.0f}%)")
    print(f"  Email addresses    : {has_email} ({has_email/total*100:.0f}%)")
    print(f"  LinkedIn URLs      : {has_li} ({has_li/total*100:.0f}%)")
    if "company_size" in df.columns:
        print(f"\n  Company size breakdown:")
        print(df["company_size"].value_counts().to_string())
    if "funding_stage" in df.columns:
        print(f"\n  Funding stage breakdown:")
        print(df["funding_stage"].value_counts().to_string())
    print("=" * 50 + "\n")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Enrich TechSparks contacts via Apollo.io")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip API calls, use mock data (for testing)")
    parser.add_argument("--limit",   type=int, default=None,
                        help="Only process first N contacts")
    parser.add_argument("--input",   default=DATA_RAW,    help="Input CSV path")
    parser.add_argument("--output",  default=DATA_ENRICHED, help="Output CSV path")
    args = parser.parse_args()

    enrich_contacts(
        input_path=args.input,
        output_path=args.output,
        dry_run=args.dry_run,
        limit=args.limit,
    )
