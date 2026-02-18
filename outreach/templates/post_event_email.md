# Post-Event Email Templates
# Timing: T+5 days after event ends (send ~Oct 3, 2024)
# Channel: Email (via Instantly.ai)
# Goal: Value-prop email + soft intro offer to YC-backed company
# Rule: Do NOT name the company — frame as "I can introduce you to a 
#       YC-backed company that specializes in solving this"
#
# Variables:
#   {{first_name}}          — contact's first name
#   {{their_company}}       — contact's company
#   {{industry_pain}}       — industry-specific pain point (from persona)
#   {{context_hook}}        — LLM-generated context hook
#   {{personalization_1}}   — Theme 1 from persona
#   {{personalization_2}}   — Theme 2 from persona
#   {{sender_name}}         — sender's name
#   {{sender_title}}        — sender's title
#   {{sender_email}}        — sender's email

---

## VARIANT A — Fintech / D2C / SaaS Founders (Primary ICP)

**Subject:** Something relevant from TechSparks week — {{first_name}}

```
Hi {{first_name}},

Hope the TechSparks energy has carried into this week.

I've been thinking about something you mentioned — {{personalization_1}}. 
It's a pattern we keep seeing with founders at {{their_company}}'s stage: 
the commercial intelligence work that should be informing pricing and 
competitive positioning is either delayed, manual, or just not happening 
at the frequency needed.

{{context_hook}}

The companies getting ahead of this are using automated data pipelines 
to do in real-time what used to take a analyst a week — monitoring 
competitor pricing, tracking assortment gaps, benchmarking before 
board reviews.

If any of this resonates, I can introduce you to a YC-backed company 
that specializes in exactly this. They work with several Indian founders 
in your category and the conversation is worth 20 minutes.

Worth a quick intro?

{{sender_name}}
{{sender_title}}
{{sender_email}}
```

**Word count:** ~160 | **Tone:** Thoughtful, value-led, single soft CTA

---

## VARIANT B — VC / PE Investors

**Subject:** Post-TechSparks — one thing worth passing to your portfolio

```
Hi {{first_name}},

Good week at TechSparks. Wanted to follow up on something I 
mentioned briefly.

{{context_hook}}

Several of your portfolio companies are likely navigating this right now — 
particularly the ones competing on price in consumer categories. 
{{personalization_1}}.

I know a YC-backed company that's built specifically for this: 
pricing intelligence, competitive benchmarking, and data automation 
for growth-stage companies. They've worked with founders across 
Elevation, Accel, and Blume portfolios.

If it's worth 15 minutes for a portfolio intro, I'm happy to make 
the connection.

{{sender_name}}
{{sender_title}}
{{sender_email}}
```

**Word count:** ~125 | **Tone:** Peer-level, portfolio angle, clear value

---

## VARIANT C — VP / Director Level (lower touch)

**Subject:** Following up from TechSparks — {{first_name}}

```
Hi {{first_name}},

Quick follow-up from last week.

We spoke briefly about {{personalization_1}} — wanted to share something 
relevant. {{context_hook}}

There's a YC-backed company I'd be happy to introduce you to if this 
is something on your radar. They work with teams your size on exactly 
this problem and keep the initial conversation very specific to your 
context.

Let me know if useful.

{{sender_name}}
```

**Word count:** ~80 | **Tone:** Light, no pressure, easy to reply to

---

## FOLLOW-UP SEQUENCE (if no reply in 5 days)

### Follow-up 1 — Day 8 post-event

**Subject:** Re: Something relevant from TechSparks week — {{first_name}}

```
Hi {{first_name}},

Just bumping this up in case it got buried.

One line version: I know a YC-backed team solving {{personalization_1}} 
for companies like {{their_company}} — happy to make the intro if 
relevant.

{{sender_name}}
```

### Follow-up 2 — Day 14 post-event (final touch)

**Subject:** Closing the loop — {{first_name}}

```
Hi {{first_name}},

Closing the loop on my earlier note. If the timing isn't right, 
completely understood — happy to reconnect when it is.

{{sender_name}}
```

---

## EMAIL DELIVERABILITY RULES
- Send from a warmed domain (not a fresh one) via Instantly.ai
- Max 30 emails/day per sending account on free trial
- SPF, DKIM, DMARC must be configured before sending
- Plain text preferred over HTML for cold email (better inbox placement)
- Unsubscribe link required (Instantly handles this automatically)

## DO NOT SEND IF
- `email` field is empty
- `confidence_flag` = LOW (human review first)
- `outreach_status` = "opted_out" or "bounced"
- `in_sequence` = TRUE
- ICP score ≤ 2
