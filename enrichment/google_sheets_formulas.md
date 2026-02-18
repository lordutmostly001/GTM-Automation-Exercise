# Google Sheets: Enrichment Formula Layer
## TechSparks GTM Automation — Step 2

This document defines every formula used in the master Google Sheet.
Import `techsparks_enriched.csv` into a sheet named **"Master"** before applying these.

---

## Sheet Structure

| Column | Header | Source | Formula / Notes |
|--------|--------|--------|-----------------|
| A | id | Step 1 | Static |
| B | name | Step 1 | Static |
| C | title | Step 1 | Static |
| D | company | Step 1 | Static |
| E | seniority_tier | Step 1 | Static (re-confirmed by Apollo) |
| F | industry_vertical | Step 1 | Static |
| G | icp_score | Step 1 | Static (1–5) |
| H | source | Step 1 | Static |
| I | linkedin_url | Apollo | Static (from enricher) |
| J | email | Apollo | Static (from enricher) |
| K | company_size | Apollo | Static |
| L | funding_stage | Apollo | Static |
| M | enrichment_status | Apollo | Static |
| N | **priority_band** | Derived | Formula ↓ |
| O | **outreach_channel** | Derived | Formula ↓ |
| P | **assigned_to** | Derived | Formula ↓ |
| Q | **sender_level** | Derived | Formula ↓ |
| R | **sequence_variant** | Derived | Formula ↓ |
| S | **linkedin_ready** | Derived | Formula ↓ |
| T | **email_ready** | Derived | Formula ↓ |
| U | **follow_up_date_pre** | Derived | Formula ↓ |
| V | **follow_up_date_post** | Derived | Formula ↓ |
| W | outreach_status | Tracking | Manual / n8n updates |
| X | in_sequence | Tracking | Manual / n8n updates |
| Y | notes | Tracking | Manual |

---

## Formulas (apply from row 2 downward)

### N2 — Priority Band
Translates ICP score into a human-readable priority tier.
```
=IFS(G2>=5,"🔴 HIGH",G2=4,"🟠 MEDIUM",G2=3,"🟡 LOW",G2<=2,"⚪ HOLD")
```

### O2 — Outreach Channel
Determines primary channel based on LinkedIn availability and ICP score.
```
=IF(AND(I2<>"",G2>=4),"LinkedIn + Email",IF(I2<>"","LinkedIn Only",IF(J2<>"","Email Only","Manual Review")))
```

### P2 — Assigned To (Owner)
Routes leads to the right owner based on seniority.
```
=IFS(E2="C-Suite","Senior AE",E2="VP/Director","AE",E2="Manager/IC","SDR",TRUE,"Unassigned")
```

### Q2 — Sender Level
Determines who the outreach should appear to come FROM (sender persona).
```
=IFS(E2="C-Suite","Leadership (VP/CEO level)",E2="VP/Director","AE",E2="Manager/IC","SDR",TRUE,"SDR")
```

### R2 — Sequence Variant
Picks which message template variant to use based on persona.
```
=IFS(
  OR(F2="Fintech",F2="D2C/Ecomm"),"Variant A: Pricing Intelligence",
  OR(F2="VC/PE"),"Variant B: Portfolio Signal Intelligence",
  OR(F2="SaaS/B2B",F2="DeepTech/AI"),"Variant C: Data Automation",
  OR(F2="Edtech",F2="Mobility"),"Variant C: Data Automation",
  TRUE,"Variant C: Data Automation"
)
```

### S2 — LinkedIn Ready
Boolean check: is this contact ready for LinkedIn outreach?
```
=IF(AND(I2<>"",W2="pending",X2="FALSE"),"✅ Ready","❌ Not Ready")
```

### T2 — Email Ready
Boolean check: is this contact ready for email outreach?
```
=IF(AND(J2<>"",W2="pending",X2="FALSE",G2>=4),"✅ Ready","❌ Not Ready")
```

### U2 — Pre-Event Follow-Up Date
7 days before event (TechSparks 2024 = Sep 26).
```
=DATE(2024,9,19)
```
*(Static for this event — update for future events)*

### V2 — Post-Event Follow-Up Date
5 days after event ends (Sep 28 + 5).
```
=DATE(2024,10,3)
```

---

## Pivot / Summary Tab Formulas
Create a second sheet named **"Summary"** with these:

### Total contacts by Priority Band
```
=COUNTIF(Master!N:N,"🔴 HIGH")   → High priority
=COUNTIF(Master!N:N,"🟠 MEDIUM") → Medium priority
=COUNTIF(Master!N:N,"🟡 LOW")    → Low priority
=COUNTIF(Master!N:N,"⚪ HOLD")   → On hold
```

### Email deliverability readiness
```
=COUNTIF(Master!T:T,"✅ Ready")
```

### LinkedIn readiness
```
=COUNTIF(Master!S:S,"✅ Ready")
```

### Contacts per owner
```
=COUNTIF(Master!P:P,"Senior AE")
=COUNTIF(Master!P:P,"AE")
=COUNTIF(Master!P:P,"SDR")
```

### Coverage by industry (example for Fintech)
```
=COUNTIF(Master!F:F,"Fintech")
```

---

## Conditional Formatting Rules

Apply to the **Master** sheet:

| Column | Rule | Format |
|--------|------|--------|
| N (Priority Band) | Text contains "HIGH" | Red background |
| N (Priority Band) | Text contains "MEDIUM" | Orange background |
| N (Priority Band) | Text contains "LOW" | Yellow background |
| N (Priority Band) | Text contains "HOLD" | Grey background |
| S / T (Ready flags) | Text contains "Ready" | Green text |
| S / T (Ready flags) | Text contains "Not Ready" | Red text |
| M (enrichment_status) | Text = "not_found" | Light red background |

---

## Data Validation Rules

| Column | Rule |
|--------|------|
| W (outreach_status) | Dropdown: pending, in_progress, sent, replied, bounced, opted_out |
| X (in_sequence) | Dropdown: TRUE / FALSE |
| E (seniority_tier) | Dropdown: C-Suite / VP-Director / Manager-IC |

---

## Import Instructions

1. Open Google Sheets → **File → Import → Upload**
2. Select `data/enriched/techsparks_enriched.csv`
3. Import type: **Replace current sheet**
4. Rename sheet tab to **"Master"**
5. Add the formulas above starting from N2, drag down to row 201
6. Create a **"Summary"** tab and add pivot formulas
7. Apply conditional formatting rules
8. Share with your team (Viewer for SDRs, Editor for AEs and above)
