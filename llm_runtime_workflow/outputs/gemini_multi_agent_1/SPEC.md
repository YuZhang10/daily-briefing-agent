# Runtime PM Spec

This briefing is designed for Jordan Chen, a PM at Cobalt Labs, to prioritize immediate operational risks, high-stakes meeting preparation, and critical industry regulatory changes. The briefing maintains a warm, efficient, and professional tone, focusing on actionable insights while strictly filtering out noise such as sports, general crypto price movements, and private calendar details. It ensures that internal product priorities and external partner escalations take precedence over general news, with a target duration of 75 seconds to ensure conciseness.

## Priority Policy
- `P0`: Immediate action-required items (PSD3 compliance, Plaid credentials) and same-day deadline-critical requests (CEO board deck review, 1:1 prep).
- `P1`: Schedule conflicts (Maya call vs. ACME interview) and direct operational escalations (Vertex Capital onboarding complaint).
- `P2`: Business context and competitive landscape (Lyra Finance growth, Cobalt Labs GA, Stripe expansion).
- `P3`: General tech industry news and non-critical team notifications.

## Must Include Bundles
- **P0 urgent_prep_and_compliance**: Align Jordan on mandatory deadlines and regulatory requirements to ensure zero-fail execution today.
  - source ids: `{"calendar": ["cal_008", "cal_009"], "emails": ["em_001", "em_002", "em_009", "em_011"], "news": ["news_002"]}`
- **P1 escalations_and_conflicts**: Flag the urgent customer onboarding issue and prompt Jordan to resolve the schedule conflict.
  - source ids: `{"calendar": ["cal_006", "cal_007"], "emails": ["em_013"]}`
- **P2 market_and_competitor_intel**: Keep Jordan informed of high-impact competitive and internal platform developments.
  - source ids: `{"calendar": ["cal_010"], "news": ["news_001", "news_003", "news_004", "news_022"]}`

## Acceptance Criteria
- Briefing must mention the board deck deadline.
- Briefing must mention the PSD3 and Plaid rotation action items.
- Briefing must flag the calendar conflict between the Maya call and the ACME interview.
- Briefing must NOT reveal private calendar details (cal_011).
- Briefing must explicitly mention Cobalt Labs' GA status.
