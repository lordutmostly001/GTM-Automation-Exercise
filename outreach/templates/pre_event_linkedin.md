# Pre-Event LinkedIn Connection Request Templates
# Timing: T-7 days before TechSparks (send ~Sep 19, 2024)
# Character limit: 300 chars (LinkedIn connection note hard limit)
# Rule: NO company name mention, NO product pitch — just a warm, relevant hook
#
# Variables (replaced by message_builder.py):
#   {{first_name}}         — contact's first name
#   {{their_company}}      — contact's company
#   {{sender_name}}        — sender's name
#   {{personalization_1}}  — Theme 1 from persona (short form)
#   {{event_hook}}         — specific hook based on industry

---

## VARIANT A — Fintech / D2C / SaaS Founders (ICP Score 5, C-Suite)

```
Hi {{first_name}}, spotted you on the TechSparks speaker list — your work 
at {{their_company}} on {{personalization_1}} caught my attention. 
Would love to connect ahead of the event. — {{sender_name}}
```

**Word count:** ~35 | **Tone:** Peer-to-peer, specific, no ask

---

## VARIANT B — VC / PE Investors (ICP Score 4–5, Partner level)

```
Hi {{first_name}}, coming across your name ahead of TechSparks — 
Elevation/Blume-stage founders I speak with are increasingly asking 
about {{personalization_1}}. Keen to connect and exchange notes. — {{sender_name}}
```

**Word count:** ~38 | **Tone:** Knowledgeable, peer-level, no ask

---

## VARIANT C — VP / Director level (ICP Score 3–4)

```
Hi {{first_name}}, attending TechSparks next week and noticed your 
background at {{their_company}}. Working on problems around 
{{personalization_1}} — would love to connect. — {{sender_name}}
```

**Word count:** ~33 | **Tone:** Direct, lightweight ask

---

## ROUTING RULES
| Seniority     | Variant | Sender Level     |
|---------------|---------|------------------|
| C-Suite       | A or B  | Leadership / VP  |
| VP/Director   | C       | AE               |
| Manager/IC    | C       | SDR              |

## DO NOT SEND IF
- `confidence_flag` = LOW
- `in_sequence` = TRUE (already in another sequence)
- `linkedin_url` is empty (no confirmed profile)
- `outreach_status` != "pending"
