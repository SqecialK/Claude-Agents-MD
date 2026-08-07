# Plan: Passive & Semi-Passive Income Operating System

## Goal / Objective

Build a repeatable, personalized system for creating multiple passive and
semi-passive income streams starting from zero capital and zero existing
audience, and grow it into a diversified portfolio of income-producing
assets through disciplined reinvestment and progressive automation.

"Passive" is a spectrum, not a binary. Every stream below is labeled by how
much ongoing attention it needs once built:

| Label | Meaning |
|---|---|
| **Active-to-build** | Requires real work up front (weeks–months) before it produces income |
| **Semi-passive** | Requires recurring light maintenance (1–5 hrs/week) once live |
| **Passive** | Requires occasional maintenance only (hours/month) once mature |

Nothing is "set and forget" at zero capital. The system's job is to move
each stream down that spectrum over time through systemization and
automation, not to promise passivity from day one.

---

## Required Inputs (Personalization Intake)

This plan cannot be correctly instantiated without these inputs. Where they
are unknown, the Logic layer MUST ask the user directly rather than assume.
Fill in / update this block before generating a personalized roadmap:

```yaml
skills:            # e.g. writing, coding, design, video editing, sales, a trade, teaching
time_budget:       # hours/week realistically available, and for how many months
capital_budget:    # cash available to invest now, and monthly after that
risk_tolerance:    # low / medium / high — capacity to lose the capital above
existing_audience: # none / small (email, social, community) / established, and where
existing_assets:   # domains, content, code, IP, equipment, licenses already owned
income_goal:       # target $/month and by what date (for realism-checking, not promising)
tax_legal_context: # country/state, entity status (sole prop/LLC/none), tax bracket if known
```

**Current known values for this user (mattkerkhoff@gmail.com):** not yet
provided. Treat all downstream recommendations in this document as the
*generic, capital/skill-tiered framework* until the intake above is
completed — at that point the Logic layer should produce a filtered,
prioritized subset (a "personal roadmap") referencing this plan rather than
duplicating it.

---

## Expected Outputs

1. A tiered menu of income-stream business models, each tagged proven vs.
   assumption, with capital/skill/time requirements.
2. A phased roadmap (Foundation → Launch → Systemize → Scale) usable
   regardless of which specific streams are chosen.
3. A marketing/audience system that feeds every stream instead of being
   rebuilt per stream.
4. An automation map: which parts of each stream can become an `operations/`
   script or a `tools/` utility, and in what order.
5. A reinvestment and diversification policy (where profit goes next).
6. A risk register of common failure modes with mitigations.
7. A review cadence so the plan self-corrects as real data comes in.

---

## Constraints and Assumptions

**Constraints**
- Start state: $0–low capital, no existing audience, unknown skill level
  (worst case assumed; adjust down once intake is filled).
- No get-rich-quick mechanics. Every stream must have a plausible, legal,
  non-exploitative path to revenue.
- No claims of guaranteed returns. Ranges given are illustrative, not
  promises.
- Nothing here constitutes individualized financial, tax, or legal advice.
  The user must confirm entity structure, tax treatment, and local
  regulations (e.g. gambling/investment license requirements, sales tax
  nexus, platform ToS) with a qualified professional before deploying
  real capital.

**Assumptions (flagged explicitly, revisit at each review)**
- The user can dedicate at least a few hours/week consistently for 3+
  months before expecting any income — this is a hard floor, not a
  pessimistic estimate.
- "From zero" means bootstrapped, not funded — no loans or investor capital
  assumed unless the intake says otherwise.
- Platform and algorithm risk (YouTube, Amazon, app stores, ad networks)
  is real and unpriced by most beginners; this plan treats single-platform
  dependence as a risk to be diversified away from, not ignored.

---

## Proven vs. Assumption — Methodology Note

Every business model below is tagged:

- **PROVEN** — decades or years of publicly documented individuals/companies
  earning real income this way, mechanism is well understood, main
  variables are effort/skill/market fit, not the model itself.
- **ESTABLISHED BUT COMPETITIVE** — proven mechanism, but market is now
  saturated/professionalized, so "from zero" success takes materially
  longer or a real differentiation angle.
- **EMERGING / ASSUMPTION** — plausible and reported by some practitioners,
  but limited long-term track record, high variance, or dependent on a
  trend (e.g. a specific AI product wave) that may not persist. Treat
  return estimates here as speculative.

Do not let a stream's excitement outrank its tag when allocating time or
capital.

---

## The Operating System Overview

Map this income-generation effort onto the repo's own PLOT layers so it's
buildable, not just aspirational:

- **Plan** (this file + any per-stream plan files added later, e.g.
  `plans/stream-<name>.md`): what each stream is, its inputs/outputs,
  success criteria.
- **Logic** (the assistant, per session): decides which stream to work on
  next, which operation/tool to invoke, adapts when something fails,
  asks the user for missing inputs instead of guessing.
- **Operations** (`operations/`, Python, deterministic): the parts of each
  stream that *can* be scripted — content publishing, data pulls, report
  generation, email sends, price/rank monitoring, bookkeeping exports.
- **Tools** (`tools/`, reusable): shared utilities used across multiple
  streams — e.g. a keyword-research wrapper, a retry-safe API client, an
  SEO/metadata generator, a "compounding calculator" for reinvestment math.

Rule of thumb: if a task is done the same way more than twice, it graduates
from a manual step in this plan into an `operations/` script, and if that
script's logic is reused by a second stream, the shared piece is promoted
into `tools/` — per AGENTS.md Rule 1 and the Self-Annealing Loop.

---

## Roadmap

### Phase 0 — Foundation (Weeks 1–4)

Goal: remove the reasons nothing gets shipped.

- Complete the Personalization Intake above.
- Pick **one** primary skill-based stream and **one** audience/content
  asset to start (not five streams at once — diversify after the first
  one produces real revenue, not before).
- Set up the boring infrastructure once, reused by every future stream:
  a business email, a simple bookkeeping sheet/tool, a domain/hosting
  account, a payment processor (Stripe/PayPal), and a place content lives
  (a blog, a channel, a repo — whatever fits the chosen stream).
- Define a single success metric for Phase 1 (e.g. "$1 of revenue that
  wasn't traded for my direct time," or "1,000 email subscribers").

### Phase 1 — Launch (Months 1–3)

Goal: get the first stream to produce *any* revenue, proving the mechanism
works before optimizing it.

- Ship a minimum viable version of the chosen asset (a short course, a
  small digital product, the first 10–20 pieces of content, the first
  micro-SaaS feature).
- Manually do everything that could later be automated — this generates
  the knowledge needed to write a correct `operations/` script later.
  Do not automate what you haven't done manually and successfully first.
- Start capturing an audience asset you own (email list) even if the
  distribution channel is one you don't own (social platform, marketplace).

### Phase 2 — Systemize & Automate (Months 3–9)

Goal: convert the manual Phase 1 process into semi-passive operations.

- For each repeated manual task, write an `operations/` script: publishing,
  customer follow-up emails, report generation, inventory/price checks.
- Extract anything reused across tasks into `tools/` (API wrappers,
  templating, validation, retry logic) per AGENTS.md.
- Introduce a lightweight funnel: audience → email list → offer, so
  marketing is a system, not a one-off push per launch.
- Start stream #2, chosen to reuse audience/skills/infrastructure from
  stream #1 rather than starting cold again.

### Phase 3 — Reinvest & Scale (Months 9+)

Goal: compound, diversify, and reduce single-point-of-failure risk.

- Apply the Reinvestment Policy below to profits.
- Diversify across at least 2–3 uncorrelated streams (different platform,
  different risk profile, different buyer) so one algorithm change or
  market shift doesn't zero out total income.
- Consider outsourcing the most time-consuming *non-core* task (editing,
  fulfillment, support) before outsourcing anything core to your
  differentiation.
- Re-run the intake/review cycle quarterly; kill underperforming streams
  deliberately rather than letting them linger half-maintained.

---

## Business Model Menu (Tiered by Capital & Skill)

### Tier A — $0–$200 capital, skill-based (time-for-money → productized)

- **PROVEN**: Freelance/consulting service in an existing skill, then
  productize it (fixed-scope packages, templates, SOPs) to make delivery
  faster and eventually delegable — the classic path from active income
  to semi-passive agency/productized service.
- **PROVEN**: Self-published ebooks/guides or paid PDF templates in a
  niche you have real expertise or research ability in (e.g. Amazon KDP,
  Gumroad, Payhip). Long tail, low per-unit revenue, compounds with catalog
  size.
- **PROVEN**: Online course / cohort teaching a skill you have (Teachable,
  Udemy, Skool, or your own site + Stripe). Income is semi-passive after
  the course is recorded; requires audience or marketplace discovery.
- **ESTABLISHED BUT COMPETITIVE**: Niche content site or YouTube channel
  monetized via ads + affiliate links. Works, but discovery is harder than
  in 2015; needs a genuine angle (specific expertise, unique data, or
  format) not just volume.
- **ESTABLISHED BUT COMPETITIVE**: Print-on-demand / dropshipping
  (Printful, Amazon Merch). Low barrier means low margin; winners usually
  have a design/brand edge, not just listing volume.

### Tier B — $200–$2,000 capital

- **PROVEN**: Licensing digital assets you can produce repeatedly —
  stock photography/video, music, website themes/plugins, Notion/Canva
  templates, on marketplaces (Envato, Creative Market, Etsy digital).
- **PROVEN**: Paid newsletter or community with a narrow, underserved topic
  (Substack, Ghost, Patreon). Income is recurring (subscriptions), which is
  more resilient than one-off product sales.
- **EMERGING / ASSUMPTION**: Micro-SaaS — a small software tool solving one
  narrow problem, sold on subscription. Proven as a category (many real
  solo-founder examples), but *your specific idea's* success is unproven
  until validated with paying users; treat build cost as sunk-risk capital.
- **EMERGING / ASSUMPTION**: "Automation/AI agency" services (building
  chatbots, workflow automations, content pipelines for local businesses).
  Real demand exists now, but the competitive landscape and pricing are
  still shifting quickly — do not assume today's margins persist.

### Tier C — $2,000+ capital (only after Tier A/B has proven cash flow)

- **PROVEN**: Dividend-paying index funds / ETFs as a *store*, not
  generator, of new passive income — realistic yields are low
  single-digit percent annually; this is a compounding vehicle for profits
  from other streams, not a primary income engine from zero.
- **PROVEN**: Real estate income via REITs or fractional platforms (lower
  capital, lower control) vs. direct rental property (higher capital,
  higher control and management burden — not truly passive without a
  property manager, which itself costs money).
- **EMERGING / ASSUMPTION**: Revenue-share investments in others' vetted
  small businesses/creators (via crowdfunding-style platforms). Track
  record is short; treat principal as fully at risk.

Explicitly **not recommended as an income *strategy*** at any tier:
speculative crypto trading, NFT flipping, MLM/affiliate-recruitment
schemes, and anything promising fixed high daily/weekly returns — these
fail the "plausible, legal, non-exploitative, evidence-based" bar in the
Constraints section above.

---

## Marketing & Audience Systems

Treat audience-building as its own asset, independent of any one stream,
because it's the highest-leverage compounding input you own:

- Pick **one** primary channel first (e.g. one social platform, or SEO
  content, or email) and get it working before adding a second — spreading
  thin across five channels at zero audience produces zero anywhere.
- Every piece of content/offer should route to an **owned** asset (email
  list) — rented platforms (social algorithms, marketplaces) can change
  terms or reach without notice; this is proven risk, not paranoia.
- Build a simple content system: pillar topics → repurposing rules (one
  long piece → several short pieces) → publishing cadence. This is where
  an `operations/` script (scheduling/cross-posting) pays off early.
- Track one leading metric per channel (email signups, watch time,
  conversion rate) instead of vanity metrics (followers) to decide what to
  double down on.

---

## Automation Systems (What Becomes Code, and When)

Only automate a step once it has been done manually, successfully, and
repeatedly (Phase 2, not Phase 0). Candidate order, roughly cheapest-to-automate
first:

1. Scheduling/publishing content across channels.
2. Email sequences (welcome, nurture, launch) triggered by list events.
3. Order/delivery fulfillment for digital products (automatic download
   links, license keys).
4. Basic bookkeeping: categorizing income/expenses from bank/Stripe
   exports into a report.
5. Monitoring: rank/price/ad-spend/traffic alerts so problems surface
   without manual checking.
6. Customer support triage (canned responses, FAQ bot) — only after
   support volume justifies it; premature automation here damages trust.

Each of these, once specified, becomes its own `operations/<name>.py` per
AGENTS.md, with shared pieces (API auth, retries, templating) promoted to
`tools/`.

---

## Reinvestment & Capital Allocation Framework

A simple, disciplined default split for profit from any stream once it's
net-positive (adjust with the user's actual risk tolerance from intake):

- **50%** back into the stream that generated it (ads, tools, outsourcing
  the next bottleneck) — double down on what's proven to work first.
- **25%** into building/validating the *next* stream (diversification).
- **15%** into low-risk compounding (index funds / debt paydown if
  applicable) — separates "the business" from "the war chest."
- **10%** reserved as a buffer/emergency fund for the streams themselves
  (ad account holds, chargebacks, tool price hikes).

This is a **starting default, not a rule** — it must be revisited once the
Required Inputs (especially `risk_tolerance` and `income_goal`) are known.

---

## Risk Management & Diversification

- No single stream should represent >60% of total income once 2+ streams
  are live — forces diversification instead of over-optimizing one channel.
- No single platform/marketplace should be a hard dependency for both
  distribution *and* payment for the same stream where avoidable (e.g.
  don't rely solely on one ad network's account staying in good standing).
- Revisit every stream's unit economics quarterly: if time-in ≫ value-out
  and isn't improving, that's a signal to systemize harder or sunset it,
  not to push through indefinitely.

---

## Metrics, Review Cadence & Self-Annealing

- **Weekly**: 15-minute check — did last week's committed action for the
  active Phase actually happen? If not, why (time, skill gap, unclear
  next step)?
- **Monthly**: revenue, time spent, and "$ per hour invested" per stream.
  This is the real passivity metric over time — it should trend up.
- **Quarterly**: re-run the Personalization Intake, re-check tags in the
  Business Model Menu still apply (markets shift), and update this plan
  file per AGENTS.md Rule 3 (plans are living documents, but only updated
  deliberately, not overwritten wholesale).

Per AGENTS.md's Self-Annealing Loop: when a stream or tactic fails, record
what broke, fix the underlying operation/tool if one exists, and update
this plan's assumptions — don't just retry the same approach unchanged.

---

## Known Edge Cases and Failure Modes

- **Shiny-object switching**: jumping streams before Phase 1 completes
  resets the clock on all of them. Mitigation: hard rule — one primary
  stream until it hits its Phase 1 success metric.
- **Automating too early**: scripting a process before it's proven wastes
  build time on a workflow likely to change. Mitigation: manual-first rule
  above.
- **Platform/algorithm dependency risk**: a channel, marketplace, or ad
  account can be demonetized, banned, or de-ranked without warning.
  Mitigation: owned audience (email) + diversification requirement above.
- **Underpriced time cost mistaken for "passive"**: a stream needing 10
  hrs/week of upkeep is semi-passive labor, not passive income — mislabeling
  it leads to burnout. Mitigation: track $/hour monthly (see Metrics).
- **Tax/legal blind spots**: crossing into business-income territory
  triggers filing obligations (estimated taxes, sales tax nexus, business
  licensing) that differ by jurisdiction. Mitigation: confirm
  `tax_legal_context` in intake and consult a professional before scaling
  revenue meaningfully.
- **Survivorship bias in "proven" examples**: publicly visible success
  stories overrepresent winners. Mitigation: the Proven/Established/
  Emerging tagging above exists specifically to counter this — treat tags
  as ceilings on confidence, not floors on expected outcome.
- **Capital risk in Tier C**: any capital markets or revenue-share
  investment can lose principal; only deploy money here that survives
  being fully lost without affecting Tier A/B operations.

---

## Allowed Operations and Tools

This plan does not yet require automation — Phase 0/1 are manual by design.
When Phase 2 is reached, the Logic layer may create, under existing
directories:

- `operations/` — one script per automatable task listed in "Automation
  Systems" above (e.g. `operations/publish_content.py`,
  `operations/send_email_sequence.py`,
  `operations/generate_income_report.py`). Each MUST be deterministic,
  testable, and read secrets from `.env` per AGENTS.md.
- `tools/` — shared utilities discovered while building the above (API
  clients, retry wrappers, a reinvestment/compounding calculator, a
  metrics aggregator). Extract per AGENTS.md's Rule 1 and the "Critical
  Rule" in the Tools section — only after a second stream needs the same
  logic.

No operations or tools exist yet for this plan (`operations/` and
`tools/` currently contain only `.gitkeep`). Build them incrementally,
per stream, as Phase 2 is reached for each — not speculatively ahead of
real, validated need.
