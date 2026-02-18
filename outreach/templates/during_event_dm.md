# During-Event LinkedIn DM Templates
# Timing: T+0 to T+2 (Sep 26–28, 2024, during TechSparks)
# Trigger: After LinkedIn connection is accepted OR on Day 1 of event
# Context: Reference something specific — their session, panel, or company news
#
# Variables:
#   {{first_name}}          — contact's first name
#   {{their_company}}       — contact's company
#   {{session_topic}}       — their talk/panel topic (pull from agenda if available, else use industry)
#   {{context_hook}}        — persona context_hook from LLM (shortened)
#   {{personalization_1}}   — Theme 1 from persona
#   {{sender_name}}         — sender's name
#   {{sender_title}}        — sender's title

---

## VARIANT A — Fintech / D2C / SaaS Founders

**Subject line (if via InMail):** Quick note from TechSparks

```
Hey {{first_name}},

Great connecting — really interesting perspective from your session on 
{{session_topic}}.

The challenge you touched on around {{personalization_1}} is something we 
keep hearing from founders at your stage. {{context_hook}}

Not pitching anything — just thought it was directly relevant to what you're 
navigating. Happy to share what we're seeing across similar companies if useful.

{{sender_name}}
{{sender_title}}
```

**Word count:** ~75 | **Tone:** Warm, insight-led, zero pressure

---

## VARIANT B — VC / PE Investors

```
Hey {{first_name}},

Appreciated connecting. Your firm's portfolio composition is interesting — 
particularly given how many of your companies are competing in price-sensitive 
categories right now.

{{context_hook}}

Worth a 20-min call to share what we're seeing across the ecosystem? Might be 
useful context for a couple of your portfolio founders specifically.

{{sender_name}}
{{sender_title}}
```

**Word count:** ~65 | **Tone:** Peer-level, value-first, clear ask

---

## VARIANT C — VP / Director Level

```
Hey {{first_name}},

Good to connect at TechSparks. Enjoyed the energy around {{session_topic}} 
today.

Quick question — is {{personalization_1}} something your team is actively 
working through right now? We've been talking to a few folks here with the 
same challenge and there's a pattern worth sharing.

{{sender_name}}
```

**Word count:** ~55 | **Tone:** Conversational, question-led

---

## FALLBACK — If connection not accepted by Day 2

Skip the DM. Move directly to post-event email sequence.
Do NOT send both a DM and an email during the event window — double-touch 
in 48 hours reads as spam.

---

## ROUTING RULES
| Seniority     | Variant | Max DMs/Day |
|---------------|---------|-------------|
| C-Suite       | A or B  | 10          |
| VP/Director   | C       | 20          |
| Manager/IC    | C       | 20          |

## DO NOT SEND IF
- Connection request not yet accepted
- `outreach_status` = "opted_out" or "bounced"
- `in_sequence` = TRUE
