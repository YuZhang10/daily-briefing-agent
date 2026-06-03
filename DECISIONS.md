# DECISIONS

This document explains the design trade-offs for the submitted prototype. I kept it written like an engineering handoff rather than a polished project report.

## 1. Architecture

```text
inputs/*.json
    |
    v
Ingest and normalize
    |
    v
Policy engine
  - profile-aware scoring
  - privacy filtering
  - conflict detection
  - topic filtering
    |
    v
Deduper and briefing planner
  - merge repeated themes such as PSD3
  - choose a compact set of must-include items
    |
    v
Writer
  - deterministic writer in this submission
  - clear replacement point for a future LLM writer
    |
    v
Validator and metadata builder
  - duration estimate
  - TTS safety checks
  - covered and dropped item accounting
    |
    v
briefing.txt + briefing.json
```

## 2. Key Design Decisions

### Multi-step agent instead of one-shot summarization

The system should not send all four JSON files to an LLM and ask for a summary. This task is mostly about judgment: what to include, what to drop, how to respect private data, how to deduplicate repeated themes, and how to explain those choices.

The implementation is a multi-step agent pipeline:

1. Read and normalize the four input files.
2. Apply explicit profile-aware scoring and filtering.
3. Detect important edge cases such as calendar conflicts and private events.
4. Deduplicate repeated topics across calendar, email, and news.
5. Build a compact briefing plan.
6. Use a deterministic writer step to turn the plan into TTS-friendly prose.
7. Validate the final text and generate structured metadata.

### Where to use the LLM

If an LLM is used in a production version, it should sit in the writer and optional repair/critic steps, not in the first-pass selection step.

The selector should be deterministic because the user profile, privacy rules, and dropped-item reasons need to be auditable. The LLM is better used for natural language quality: turning a constrained plan into a warm, efficient spoken briefing.

This submission uses the no-API path by default. The interviewer should be able to run the project in five minutes without configuring external services.

The LLM input I would use in the next iteration would be a constrained briefing plan, not the raw JSON. The LLM would be asked to rewrite that plan into natural spoken prose while preserving required facts and avoiding URLs, email addresses, Markdown, and numeric shorthand.

### Selection and prioritization

The selection policy should strongly prioritize:

- tracked entities from the profile: Cobalt Labs, Stripe, Plaid, Lyra Finance, and Maya Chen;
- action-required and high-authority emails, especially CEO, partner, compliance, and operational-risk messages;
- calendar items that affect preparation, sequencing, or conflicts;
- fintech regulation and platform/product news relevant to Jordan's role.

The policy should drop or down-rank:

- sports and entertainment news;
- day-to-day crypto price movement, while keeping crypto regulation or enforcement;
- automated notifications and promotional emails unless they mention a tracked entity or important operational issue;
- pure AI benchmark news when it is not a product application.

### Calendar and email deduplication

Calendar and email items are not treated as interchangeable duplicates. They usually carry different parts of the same real-world event:

- the calendar item provides time, sequence, location, attendees, and conflicts;
- the email provides intent, preparation requirements, deadlines, or the latest context.

The briefing planner therefore merges them into an event bundle instead of deleting one side. For example:

- `cal_003` plus `em_002`: Priya's one-on-one plus the requested recommendation on pulling the payments API GA forward by two weeks.
- `cal_005` plus `em_003`: Stripe lunch plus the added Jess Park context and possible Stripe Issuing topic.
- `cal_006` plus `em_008`: Maya call plus birthday-planning intent.
- `cal_008` plus `em_001`: board prep plus Alex's request to review payments revenue slides before two p.m.
- `cal_009` plus `em_011` plus `news_002`: PSD3 sync plus Rahul's action-required email plus Reuters confirmation of the final EU text.

The spoken briefing should mention each bundle once, while `briefing.json` should list all covered IDs inside the relevant section. This keeps the audio short without hiding the source evidence.

### Personalization scope

The supplied data is for Jordan Chen, so the submitted output is optimized for Jordan's profile and day. The system design should still be generic: Jordan should be treated as one configured user/persona, not as hardcoded application logic.

For a production version, I would separate priority into three layers:

1. Universal consequence signals: deadlines, explicit owner, action-required labels, calendar conflicts, private/sensitive handling, security/legal/compliance risk, executive requests, and prep needed before a scheduled meeting.
2. Segment-level policy: user clusters such as product leader, on-call engineer, sales/account owner, finance/legal operator, or executive assistant can have different P0 trigger templates.
3. User-level profile: tracked entities, not-interested topics, tone, and personal exceptions.

An LLM can help mine cluster-specific trigger phrases and examples from historical data, but the final priority ladder should remain explicit and auditable. In other words, use the model to propose semantic tags or policy candidates, then let deterministic policy assign P0/P1/P2/P3.

### How the profile is applied

The profile is applied in three places:

1. Positive selection: tracked entities such as Cobalt Labs, Stripe, Plaid, Lyra Finance, and Maya Chen receive priority boosts. This is why Cobalt launch news, Stripe lunch context, Plaid credential rotation, Lyra competitive updates, and Maya's conflicting call make it into the briefing.
2. Negative filtering: topics in `not_interested` are filtered or down-ranked. Sports and entertainment are removed. Day-to-day crypto price movement is removed, while crypto regulation or enforcement can still be considered because the profile explicitly allows that exception.
3. Output constraints: the writer follows the requested tone: warm but efficient, specific, short, and TTS-friendly. The text avoids "Good morning", avoids URLs and email addresses, and writes numbers naturally.

The important design point is that profile handling is not only prompt text. Some preferences are enforced as hard policy, especially topic exclusions, privacy, tracked entities, and duration constraints.

### Known data issues found during initial read

- `cal_006` and `cal_007` overlap from one fifteen to one thirty p.m.; the briefing should surface this conflict.
- `cal_011` is private and should not expose details. It may be mentioned only as a private five p.m. appointment if needed.
- `em_020` is a personal medical appointment confirmation; the system should avoid reading medical details aloud.
- PSD3 appears in calendar, email, and news. It should be merged into one concise point, not repeated three times.
- Bitcoin price movement appears in both email and news, but the profile says to avoid day-to-day crypto price movements. It should be dropped unless tied to regulation or enforcement.
- Sports and entertainment stories are present and should be filtered.

### Duration control

The target is seventy-five seconds, with an allowed range of sixty to ninety seconds. I will estimate spoken duration using roughly one hundred fifty words per minute:

```text
estimated_seconds = word_count / 150 * 60
```

That means the final briefing should usually land around one hundred eighty to two hundred ten English words. The current generated briefing is two hundred twelve words, estimated at eighty-five seconds, which is inside the required sixty-to-ninety-second range.

### Metadata fields

`briefing.json` uses these top-level fields:

- `generated_for`: user, date, and timezone.
- `covered_item_ids`: actual input IDs covered by the spoken text, grouped by calendar, emails, and news.
- `duration_estimate`: word count, estimated seconds, and the estimation method.
- `sections`: character ranges in `briefing.txt`, with item IDs covered by each section.
- `calendar_conflicts_detected`: explicit overlap detection, currently surfacing the Maya and ACME Bank conflict.
- `dropped_items`: actively omitted items with reasons and internal scores.
- `validation`: TTS and duration checks.
- `notes`: implementation notes that help reviewers interpret the output.

### TTS friendliness

The generated `briefing.txt` should be plain spoken English:

- no Markdown markers;
- no URLs;
- no email addresses;
- numbers and units written naturally, such as "twelve percent" instead of "12%";
- varied opening, not always "Good morning";
- concise sentences because the listener has no visual context.

## 3. AI Tool Usage Log

- I used Codex as a design and implementation partner.
- Human-led decisions so far: prefer a controllable multi-step agent over one-shot summarization; keep deterministic selection and metadata for auditability; place the LLM only in writer and optional repair steps; keep a no-API fallback for reproducible evaluation.
- Codex helped read the input data, identify hidden edge cases, draft this decision log, and implement the first prototype.
- A useful correction during discussion: starting with code immediately would skip the most important part of the task, which is understanding the data traps and system design. We paused and discussed the architecture first.
- A concrete bug caught during review: the initial metadata used the selector's broader candidate set as `covered_item_ids`, so a few relevant-but-unspoken items appeared as covered. I corrected this by deriving top-level coverage from the actual section metadata, then moving those relevant-but-unspoken items into `dropped_items` with a duration-budget reason.

## 4. Known Limitations

- The first implementation uses explicit rules rather than a full production retrieval/ranking stack.
- The deterministic writer is less stylistically flexible than an LLM writer, but it is easier for reviewers to run.
- The duration estimate is based on word count, not actual TTS audio timing.
- The system will optimize for this supplied data set while keeping the architecture extensible.

## 5. If I Had Two More Hours

I would add an LLM writer and critic behind environment-variable configuration, plus snapshot tests showing that the same input produces stable item selection and metadata.
