"""
routing/lead_router.py
=======================
Assigns every contact to the right owner and sender level,
enforces deduplication across active sequences, and flags
contacts that need leadership-level outreach.

Routing logic:
  C-Suite   → Senior AE owns | Leadership sends (VP/CEO-level)
  VP/Dir    → AE owns        | AE sends
  Manager   → SDR owns       | SDR sends

Additional rules:
  - ICP 5 + C-Suite → escalate to leadership review before sending
  - Same contact cannot be in two sequences simultaneously
  - Same company cannot receive outreach from two different owners
    (avoids the embarrassing "three people from our team emailed you" problem)

HOW TO RUN:
    python routing/lead_router.py
    python routing/lead_router.py --input data/final/techsparks_outreach_ready.csv
"""

import os
import sys
import logging
import argparse
import pandas as pd
from collections import defaultdict

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import ROUTING_RULES, ICP_THRESHOLDS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

INPUT_PATH  = "data/final/techsparks_outreach_ready.csv"
OUTPUT_PATH = "data/final/techsparks_routed.csv"

# ── Team roster ───────────────────────────────────────────────────────────────
# In production: pull from CRM. Here: static for the prototype.

TEAM = {
    "Senior AE": [
        {"name": "Priya Nair",    "email": "priya@company.co",   "capacity": 30},
        {"name": "Vikram Sethi",  "email": "vikram@company.co",  "capacity": 30},
    ],
    "AE": [
        {"name": "Sneha Kapoor",  "email": "sneha@company.co",   "capacity": 50},
        {"name": "Rahul Desai",   "email": "rahul@company.co",   "capacity": 50},
        {"name": "Meera Iyer",    "email": "meera@company.co",   "capacity": 50},
    ],
    "SDR": [
        {"name": "Arjun Sharma",  "email": "arjun@company.co",   "capacity": 60},
        {"name": "Divya Menon",   "email": "divya@company.co",   "capacity": 60},
        {"name": "Karan Bose",    "email": "karan@company.co",   "capacity": 60},
    ],
}

SENDER_PERSONA = {
    "Leadership": {"name": "Rohan Mehta",  "title": "VP of Partnerships",   "email": "rohan@company.co"},
    "AE":         {"name": "Sneha Kapoor", "title": "Account Executive",     "email": "sneha@company.co"},
    "SDR":        {"name": "Arjun Sharma", "title": "Sales Development Rep", "email": "arjun@company.co"},
}


# ─────────────────────────────────────────────────────────────────────────────
# ROUTING ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class LeadRouter:
    def __init__(self, team: dict = TEAM):
        self.team             = team
        self.assignment_count = defaultdict(int)   # owner_name → assigned count
        self.company_owner    = {}                 # company_root → owner_name (prevents multi-owner per company)
        self.sequence_ids     = set()              # contact IDs already in a sequence

    def assign_owner(self, seniority: str) -> dict:
        """
        Round-robin assign within the correct role tier,
        respecting individual capacity limits.
        """
        role    = ROUTING_RULES.get(seniority, {}).get("owner_role", "SDR")
        members = self.team.get(role, self.team["SDR"])

        # Find the least-loaded member who still has capacity
        for member in sorted(members, key=lambda m: self.assignment_count[m["name"]]):
            if self.assignment_count[member["name"]] < member["capacity"]:
                self.assignment_count[member["name"]] += 1
                return {"owner_name": member["name"], "owner_email": member["email"], "owner_role": role}

        # All at capacity — assign to first member anyway, flag it
        log.warning(f"[CAPACITY] All {role}s at capacity — overflowing to {members[0]['name']}")
        self.assignment_count[members[0]["name"]] += 1
        return {"owner_name": members[0]["name"], "owner_email": members[0]["email"],
                "owner_role": role, "capacity_overflow": True}

    def get_sender(self, seniority: str) -> dict:
        """Return the sender persona for the outreach (who the email appears to come from)."""
        sender_level = ROUTING_RULES.get(seniority, {}).get("sender_level", "SDR")
        return SENDER_PERSONA.get(sender_level, SENDER_PERSONA["SDR"])

    def needs_leadership_review(self, contact: dict) -> bool:
        """
        Flag contacts that should be reviewed by leadership before outreach.
        Rule: ICP 5 AND C-Suite → leadership must approve the message.
        """
        return (
            contact.get("icp_score", 0) >= ICP_THRESHOLDS["high"] and
            contact.get("seniority_tier") == "C-Suite"
        )

    def check_company_conflict(self, contact: dict) -> tuple[bool, str]:
        """
        Prevent two different owners from contacting the same company.
        Returns (conflict_exists, existing_owner_name).
        """
        company_root = str(contact.get("company","")).lower().split()[0]
        if company_root in self.company_owner:
            existing = self.company_owner[company_root]
            return True, existing
        return False, ""

    def check_duplicate_sequence(self, contact: dict) -> bool:
        """Return True if this contact is already in an active sequence."""
        return str(contact.get("id","")) in self.sequence_ids

    def route(self, contact: dict) -> dict:
        """
        Run the full routing logic for a single contact.
        Returns a dict of routing fields to merge into the contact row.
        """
        contact_id = str(contact.get("id",""))
        seniority  = contact.get("seniority_tier","Manager/IC")
        result     = {
            "owner_name":          "",
            "owner_email":         "",
            "owner_role":          "",
            "sender_name":         "",
            "sender_title":        "",
            "sender_email":        "",
            "routing_status":      "assigned",
            "leadership_review":   "NO",
            "routing_notes":       "",
            "capacity_overflow":   False,
        }

        # ── Gate 1: Already in sequence ───────────────────────────────────
        if self.check_duplicate_sequence(contact):
            result["routing_status"] = "skip_in_sequence"
            result["routing_notes"]  = "Contact already in an active sequence"
            log.info(f"[SKIP] {contact.get('name')} — already in sequence")
            return result

        # ── Gate 2: Company conflict ──────────────────────────────────────
        conflict, existing_owner = self.check_company_conflict(contact)
        if conflict:
            result["routing_status"] = "skip_company_conflict"
            result["routing_notes"]  = f"Company already owned by {existing_owner}"
            result["owner_name"]     = existing_owner
            log.info(f"[CONFLICT] {contact.get('name')} @ {contact.get('company')} — routed to existing owner {existing_owner}")
            return result

        # ── Assign owner ──────────────────────────────────────────────────
        assignment = self.assign_owner(seniority)
        result.update(assignment)

        # ── Assign sender ─────────────────────────────────────────────────
        sender = self.get_sender(seniority)
        result["sender_name"]  = sender["name"]
        result["sender_title"] = sender["title"]
        result["sender_email"] = sender["email"]

        # ── Leadership review flag ────────────────────────────────────────
        if self.needs_leadership_review(contact):
            result["leadership_review"] = "YES"
            result["routing_notes"]     = "ICP 5 + C-Suite — leadership must approve before send"
            log.info(f"[ESCALATE] {contact.get('name')} — flagged for leadership review")

        # ── Register company ownership ────────────────────────────────────
        company_root = str(contact.get("company","")).lower().split()[0]
        self.company_owner[company_root] = result["owner_name"]

        # ── Register in sequence ──────────────────────────────────────────
        self.sequence_ids.add(contact_id)

        log.info(f"[ASSIGNED] {contact.get('name')} → {result['owner_name']} "
                 f"({'ESCALATE' if result['leadership_review']=='YES' else 'standard'})")
        return result


# ─────────────────────────────────────────────────────────────────────────────
# ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────

def route_all(
    input_path:  str = INPUT_PATH,
    output_path: str = OUTPUT_PATH,
) -> pd.DataFrame:

    log.info(f"Loading: {input_path}")
    df = pd.read_csv(input_path)

    # Process highest ICP first — they get first pick of owner capacity
    df = df.sort_values(["icp_score","seniority_tier"], ascending=[False, True]).reset_index(drop=True)

    router  = LeadRouter()
    results = []

    for _, row in df.iterrows():
        contact = row.to_dict()
        routing = router.route(contact)
        results.append({**contact, **routing})

    out_df = pd.DataFrame(results)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    out_df.to_csv(output_path, index=False)
    log.info(f"✅ Routed contacts saved → {output_path}")

    _print_summary(out_df, router)
    return out_df


def _print_summary(df: pd.DataFrame, router: LeadRouter):
    total      = len(df)
    assigned   = (df["routing_status"] == "assigned").sum()
    escalated  = (df["leadership_review"] == "YES").sum()
    conflicts  = (df["routing_status"] == "skip_company_conflict").sum()
    in_seq     = (df["routing_status"] == "skip_in_sequence").sum()

    print(f"\n{'='*55}")
    print(f"  LEAD ROUTING SUMMARY")
    print(f"{'='*55}")
    print(f"  Total contacts         : {total}")
    print(f"  Assigned               : {assigned}")
    print(f"  Needs leadership review: {escalated}")
    print(f"  Company conflicts      : {conflicts}")
    print(f"  Already in sequence    : {in_seq}")

    print(f"\n  Owner workload:")
    for owner, count in sorted(router.assignment_count.items(), key=lambda x: -x[1]):
        print(f"    {owner:<20} {count} contacts")

    print(f"\n  By owner role:")
    print(df["owner_role"].value_counts().to_string())

    print(f"\n  Leadership review queue (ICP 5, C-Suite):")
    escalated_df = df[df["leadership_review"] == "YES"][["name","company","icp_score","owner_name"]]
    print(escalated_df.head(10).to_string(index=False))
    print(f"{'='*55}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",  default=INPUT_PATH)
    parser.add_argument("--output", default=OUTPUT_PATH)
    args = parser.parse_args()
    route_all(args.input, args.output)
