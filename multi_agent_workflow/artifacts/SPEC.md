# Daily Briefing PM Spec

## Product Goal

Generate a warm, efficient, eyes-free morning audio briefing for Jordan Chen that turns today's calendar, recent email, and news into a 60-90 second consequence-aware plan. The briefing should not summarize everything. It should tell Jordan what could cause missed prep, missed decisions, conflicts, owner risk, partner/customer risk, compliance exposure, or lost context around tracked entities, with each spoken claim traceable to concrete input IDs.

## Listener Persona And Constraints

- Jordan Chen is a Senior Product Manager on Cobalt Labs' Payments Platform team.
- The briefing is heard at 7:30 a.m. Pacific on 2026-05-15, before an 8:30 a.m. standup and a dense day of meetings.
- Jordan cannot see the text. Output must be English, spoken naturally, and useful without visual context.
- Target length is 75 seconds, with a hard acceptable range of 60-90 seconds.
- Tone: warm but efficient, like a thoughtful chief of staff. Avoid filler and hedging.
- Interests: Cobalt Labs payments launch, fintech regulation, Stripe, Plaid, Lyra Finance, applied AI/product, developer tools, product analytics.
- Non-interests: celebrity/entertainment, sports scores/standings, and crypto price moves unless regulation or enforcement is involved.
- Tracked entities need strong preference: Cobalt Labs and Maya Chen are always-include entities; Stripe, Plaid, and Lyra Finance should be included when there is operational, partner, or competitive consequence.

## Briefing Success Criteria

- Jordan knows the most important next actions before the workday starts.
- P0 items are spoken unless privacy constraints require a masked mention.
- The 1:00 p.m. conflict between Maya and the customer interview is surfaced.
- Same-event items are bundled once, not repeated across calendar, email, and news.
- Every spoken topic has a consequence, preparation implication, or tracked-entity reason.
- The final `briefing.json` explains included IDs, dropped IDs, estimated duration, segment ranges, and deduplication decisions.
- The spoken text contains no Markdown, URLs, or email addresses.

## Priority Definitions

### P0 - Must Speak

Missing this could cause real harm: missed same-day preparation, missed deadline, calendar conflict, executive visibility, compliance/legal/security exposure, ownership risk, or blocking another team.

Use these as P0 anchors:

- `cal_002`, `cal_003`, `em_002`, `em_004`: 9:00 roadmap review where Jordan owns the agenda, followed by Priya's 10:30 request for a recommendation on pulling GA forward.
- `cal_008`, `em_001`: 2:00 board prep with the CEO; slides 8-14 and ARR projection need review before then.
- `cal_009`, `em_011`, `news_002`: 3:00 PSD3 compliance sync; final text changes SCA exemptions and fraud-data-sharing obligations.
- `em_009`: Plaid credential rotation is action-required by 2026-05-20 and Jordan is listed owner.
- `cal_006`, `em_008`, `cal_007`: Maya call at 1:00 conflicts with the 1:15 customer interview; Maya is always include and the conflict needs resolution.
- `news_001`: Cobalt Labs payments GA is public, directly tied to Jordan's product area, and names Stripe as a partner.

### P1 - Speak If Room After P0

Important for decision quality, external relationships, customer risk, competitive context, or tracked entities, but lower immediate harm than P0.

Examples:

- `cal_005`, `em_003`, `news_004`: Stripe lunch, Jess Park joining, and Stripe Issuing expansion give Jordan partner context.
- `cal_010`, `news_003`, `news_022`: Lyra competitive teardown plus Series C and new president signal competitive pressure.
- `news_005`: Plaid lawsuit is vendor/reputational context, separate from the credential rotation action.
- `em_013`: Vertex Capital onboarding escalation needs product input by Monday.
- `em_016`: PR review on USD-to-JPY rounding bug may need product-owner attention.

### P2 - Metadata First, Audio Only On Light Days

Relevant to Jordan's interests but not tied to a same-day action or high consequence. These can be omitted from audio if P0/P1 fill the time budget.

Examples:

- `news_009`: crypto enforcement action, allowed by the exception to the crypto-price dislike.
- `news_011`, `news_013`, `news_024`, `news_027`: applied AI/developer-tool/product news.
- `news_014`, `news_021`, `news_028`: fintech/regulatory context without a direct same-day action.
- `em_006`, `em_007`: potentially useful business context but not immediate ownership unless paired with a stronger event.

### P3 - Drop By Default

Low consequence, duplicated, off-preference, automated, promotional, or private-detail content.

Examples:

- `cal_001`: recurring standup with no special consequence.
- `cal_004`: focus block is schedule context only; include only if it affects prep sequencing.
- `em_005`, `em_012`, `em_014`, `em_015`, `em_017`, `em_018`: automated, promotional, mass, or low-signal group content.
- `news_006`, `news_007`, `news_019`, `news_029`: sports or entertainment.
- `news_008`, `em_019`: crypto price movement; drop despite financial interest.
- `news_016`: pure benchmark AI news; not product-application focused enough.

## Must-Include Themes

- Same-day prep and ownership: roadmap agenda, Priya recommendation, board slide review, PSD3 read-ahead.
- Consequence-bearing conflicts: Maya at 1:00 versus ACME Bank at 1:15.
- Action-required deadlines: Plaid credential rotation by May 20.
- Public Cobalt Labs payments launch coverage.
- Tracked partner/competitor context when compressed: Stripe Issuing context for lunch, Lyra funding/executive hire for competitive teardown.

## Must-Drop Themes

- Sports scores and standings: `news_006`, `news_029`.
- Celebrity and entertainment news: `news_007`, `news_019`.
- Crypto price moves without regulation/enforcement: `news_008`, `em_019`.
- Promotional, recruiter, digest, and automated noise unless used as evidence in a higher-priority bundle: `em_005`, `em_012`, `em_015`, `em_017`, `em_018`.
- Private medical/provider details from `cal_011` and `em_020`.
- Low-signal social coordination like `em_014` unless the day is otherwise empty.

## Privacy Constraints

- `cal_011` and `em_020` may only be surfaced as "a private appointment at five" if schedule context matters. Do not mention Sutter Health, medical, provider, location, or appointment type.
- `cal_006` and `em_008` should be surfaced because Maya is tracked and there is a conflict, but avoid birthday, restaurant, or surprise-party details in the spoken briefing.
- Do not speak email addresses, URLs, or unnecessary attendee lists.
- Metadata may reference input IDs and high-level reasons, but should not copy sensitive personal summaries verbatim.

## TTS Constraints

- `briefing.txt` must be plain text only: no Markdown, bullets, URLs, email addresses, or section labels.
- Use oral numbers: "four billion", "eighty million", "one point two billion", "May twentieth", "two p.m.", "twenty-three percent".
- Expand or explain acronyms when helpful for listening: "strong customer authentication" before "SCA" if used at all.
- Keep sentences short enough for audio. Prefer concrete verbs: "review", "decide", "resolve", "skim", "ask".
- Vary the opening. Do not start every day with "Good morning."
- Target roughly 170-200 words at about 150 words per minute.

## Metadata Requirements

`briefing.json` should include at minimum:

- `date`, `timezone`, `generated_for`, and duration settings from `profile.json`.
- `estimated_duration_seconds`, `word_count`, and `estimation_method`.
- `sections` with names, character or line ranges into `briefing.txt`, and covered input IDs.
- `covered_items` grouped by `calendar`, `emails`, and `news`.
- `bundles` with `bundle_id`, priority, spoken/not spoken status, source IDs, and reason.
- `dropped_items` with item ID, source type, priority/drop rule, and concise reason.
- `privacy_transformations` for `cal_011`, `em_020`, `cal_006`, and `em_008` if referenced.
- `deduplication` records showing which IDs were merged, especially PSD3, Stripe, Lyra, board prep, Maya conflict, and Cobalt launch where applicable.

## Acceptance Checklist For Engineer Agent

- Reads all four input JSON files and does not modify them.
- Produces `briefing.txt` and `briefing.json` at project root.
- Audio text is English, natural, plain text, and 60-90 seconds by the stated estimator.
- All P0 bundles are either spoken or explicitly omitted with a reason in metadata.
- No URL, email address, Markdown marker, or private medical detail appears in `briefing.txt`.
- Same-event sources are spoken once and represented as merged bundles in metadata.
- Dropped items include concrete reasons, not generic "not relevant" placeholders.
- Cobalt Labs, Maya, Stripe, Plaid, and Lyra handling follows the priority policy.
- The briefing does not mention sports, entertainment, or crypto price movement unless the policy exception applies.
