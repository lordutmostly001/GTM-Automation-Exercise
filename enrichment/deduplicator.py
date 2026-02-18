"""
enrichment/deduplicator.py
===========================
Detects and resolves duplicate contacts in the master list.

Duplicates arise from:
  1. Same person scraped + added to mock list
  2. Name variations: "Dr. Rohini Srivathsa" vs "Rohini Srivathsa"
  3. Company variations: "Razorpay" vs "Razorpay India Pvt Ltd"
  4. Scaling scenario: merging two event lists

Strategy:
  - Exact match on normalized (name + company) → definite duplicate
  - Fuzzy match (Levenshtein similarity ≥ threshold) → probable duplicate
  - Keep: highest ICP score, or first occurrence if scores are equal
  - Flag: don't silently delete — write all duplicates to a separate file

HOW TO RUN:
    python enrichment/deduplicator.py                          # default paths
    python enrichment/deduplicator.py --input data/raw/x.csv  # custom input
"""

import os
import re
import sys
import logging
import pandas as pd
from difflib import SequenceMatcher

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import DATA_ENRICHED, DEDUP_SETTINGS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


# ── Text normalisation helpers ────────────────────────────────────────────────

# Honorifics to strip before comparison
HONORIFICS = re.compile(
    r"^(dr\.?|mr\.?|mrs\.?|ms\.?|prof\.?|shri\.?|smt\.?)\s+",
    flags=re.IGNORECASE,
)

# Company suffixes to strip
CO_SUFFIXES = re.compile(
    r"\s+(india|pvt\.?|ltd\.?|limited|private|inc\.?|llc|group|technologies|tech|solutions)\b",
    flags=re.IGNORECASE,
)


def normalize_name(name: str) -> str:
    """
    Strip honorifics, lowercase, remove punctuation.
    'Dr. Sreedhara Panicker Somanath' → 'sreedhara panicker somanath'
    """
    name = HONORIFICS.sub("", str(name).strip())
    name = re.sub(r"[^\w\s]", "", name)
    return name.lower().strip()


def normalize_company(company: str) -> str:
    """
    Strip common suffixes, lowercase.
    'Razorpay India Pvt Ltd' → 'razorpay'
    """
    company = CO_SUFFIXES.sub("", str(company).strip())
    company = re.sub(r"[^\w\s]", "", company)
    return company.lower().strip().split()[0] if company.strip() else ""


def similarity(a: str, b: str) -> float:
    """Levenshtein-based similarity ratio, 0.0–1.0."""
    return SequenceMatcher(None, a, b).ratio() * 100


def dedup_key(row) -> str:
    """Composite key for exact dedup: normalized_name + "|" + normalized_company_first_word."""
    return normalize_name(row["name"]) + "|" + normalize_company(row["company"])


# ── Core dedup logic ──────────────────────────────────────────────────────────

def find_duplicates(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Identify exact and fuzzy duplicate contacts.

    Returns:
        (clean_df, duplicates_df)
        clean_df:      Deduplicated contacts (one record per person)
        duplicates_df: All flagged duplicates with reason and kept_id
    """
    threshold = DEDUP_SETTINGS["fuzzy_threshold"]
    strategy  = DEDUP_SETTINGS["merge_strategy"]

    df = df.copy().reset_index(drop=True)
    df["_key"] = df.apply(dedup_key, axis=1)

    kept_indices   = []   # indices of records we'll keep
    dup_records    = []   # records flagged as duplicates
    processed_keys = {}   # key → kept_index

    for i, row in df.iterrows():
        key     = row["_key"]
        matched = False

        # ── 1. Exact key match ────────────────────────────────────────────────
        if key in processed_keys:
            kept_idx = processed_keys[key]
            log.info(f"[EXACT DUP] '{row['name']}' @ '{row['company']}' "
                     f"matches row {kept_idx}")
            dup_records.append({
                **row.to_dict(),
                "dup_reason": "exact_match",
                "kept_id":    df.loc[kept_idx, "id"],
            })
            matched = True

        # ── 2. Fuzzy name match (same company first word) ─────────────────────
        if not matched:
            norm_name    = normalize_name(row["name"])
            norm_company = normalize_company(row["company"])

            for existing_key, kept_idx in processed_keys.items():
                ex_name, ex_co = existing_key.split("|", 1)

                # Only compare if company root matches (avoids false positives)
                if ex_co != norm_company:
                    continue

                name_sim = similarity(norm_name, ex_name)
                if name_sim >= threshold:
                    log.info(f"[FUZZY DUP] '{row['name']}' ≈ '{df.loc[kept_idx, 'name']}' "
                             f"(similarity: {name_sim:.0f}%)")
                    dup_records.append({
                        **row.to_dict(),
                        "dup_reason": f"fuzzy_match_{name_sim:.0f}pct",
                        "kept_id":    df.loc[kept_idx, "id"],
                    })
                    matched = True
                    break

        # ── 3. Keep this record ───────────────────────────────────────────────
        if not matched:
            # If merge_strategy = keep_highest_icp, swap if new record scores higher
            if strategy == "keep_highest_icp" and key in processed_keys:
                existing_idx = processed_keys[key]
                if row.get("icp_score", 0) > df.loc[existing_idx, "icp_score"]:
                    # Demote the previously kept record
                    dup_records.append({
                        **df.loc[existing_idx].to_dict(),
                        "dup_reason": "replaced_by_higher_icp",
                        "kept_id":    row["id"],
                    })
                    kept_indices.remove(existing_idx)
                    kept_indices.append(i)
                    processed_keys[key] = i
            else:
                kept_indices.append(i)
                processed_keys[key] = i

    clean_df = df.loc[kept_indices].drop(columns=["_key"]).reset_index(drop=True)
    dups_df  = pd.DataFrame(dup_records).drop(columns=["_key"], errors="ignore")

    return clean_df, dups_df


# ── Main orchestrator ─────────────────────────────────────────────────────────

def deduplicate(
    input_path:  str = DATA_ENRICHED,
    output_path: str = None,
) -> pd.DataFrame:
    """
    Load enriched CSV, deduplicate, save clean + duplicates CSVs.

    Returns clean DataFrame.
    """
    if output_path is None:
        output_path = input_path  # overwrite in place

    dups_path = output_path.replace(".csv", "_duplicates_flagged.csv")

    log.info(f"Loading: {input_path}")
    df = pd.read_csv(input_path)
    original_count = len(df)

    log.info(f"Starting dedup on {original_count} contacts...")
    clean_df, dups_df = find_duplicates(df)

    removed = original_count - len(clean_df)
    log.info(f"Dedup complete: {removed} duplicates removed, {len(clean_df)} clean records")

    # Save outputs
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    clean_df.to_csv(output_path, index=False)
    log.info(f"✅ Clean contacts saved: {output_path}")

    if not dups_df.empty:
        dups_df.to_csv(dups_path, index=False)
        log.info(f"⚠️  Duplicates flagged: {dups_path} ({len(dups_df)} records)")

    _print_summary(original_count, clean_df, dups_df)
    return clean_df


def _print_summary(original: int, clean: pd.DataFrame, dups: pd.DataFrame):
    print("\n" + "=" * 50)
    print("  DEDUPLICATION SUMMARY")
    print("=" * 50)
    print(f"  Original contacts  : {original}")
    print(f"  After dedup        : {len(clean)}")
    print(f"  Duplicates removed : {original - len(clean)}")
    if not dups.empty and "dup_reason" in dups.columns:
        print(f"\n  Duplicate reasons:")
        print(dups["dup_reason"].value_counts().to_string())
    print("=" * 50 + "\n")


# ── Scale scenario: merge two lists ──────────────────────────────────────────

def merge_and_dedup(list_a_path: str, list_b_path: str, output_path: str) -> pd.DataFrame:
    """
    Merge two contact CSVs (e.g., two event lists) and deduplicate.
    Handles scaling from 200 → 2000 contacts.

    Args:
        list_a_path: Primary list (higher priority on conflicts)
        list_b_path: Secondary list
        output_path: Where to write merged + deduped result

    Returns:
        Merged and deduplicated DataFrame
    """
    log.info(f"Merging:\n  A: {list_a_path}\n  B: {list_b_path}")

    df_a = pd.read_csv(list_a_path)
    df_b = pd.read_csv(list_b_path)

    # Tag source before merging so we can trace origin
    df_a["merge_source"] = "list_a"
    df_b["merge_source"] = "list_b"

    # Re-index list_b IDs to avoid collisions
    df_b["id"] = df_b["id"] + df_a["id"].max()

    merged = pd.concat([df_a, df_b], ignore_index=True)
    log.info(f"Merged {len(df_a)} + {len(df_b)} = {len(merged)} contacts. Deduplicating...")

    return deduplicate(input_path=None, output_path=output_path)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Deduplicate enriched contact list")
    parser.add_argument("--input",  default=DATA_ENRICHED, help="Input CSV")
    parser.add_argument("--output", default=None,          help="Output CSV (default: overwrite input)")
    parser.add_argument("--merge-b", default=None,         help="Second list to merge (scale scenario)")
    args = parser.parse_args()

    if args.merge_b:
        out = args.output or DATA_ENRICHED.replace(".csv", "_merged.csv")
        merge_and_dedup(args.input, args.merge_b, out)
    else:
        deduplicate(input_path=args.input, output_path=args.output)
