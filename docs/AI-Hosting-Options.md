# GlowStar Chatbot — AI Hosting Options

**Prepared:** August 10, 2026 · **Fully re-verified:** August 13, 2026
**Purpose:** Compare ways to run the AI model behind the chatbot, so we can pick one together.

This document lays out every realistic option, what each one costs, and — most importantly — **where your data goes** in each case, since that was the main concern raised earlier. All prices were re-checked directly against each provider's official pricing page on **August 13, 2026**. The per-question cost is based on a **directly measured** real question, not an estimate.

Exchange rate: **$1 = ₹95.34** (Aug 13, 2026). Previous version used ₹95.44.

---

## What changed since the August 11 version

Four things changed, and two of them change the recommendation. Read this section before the tables.

| Change | Impact |
|---|---|
| **DeepInfra cut Qwen 3.5-9B input pricing** from $0.10 → **$0.04**/1M (output rose $0.15 → $0.20) | Per-question cost **halved**: ₹1.52 → **₹0.72**. This workload is input-heavy, so the input cut dominates. |
| **JarvisLabs now publishes direct INR pricing** and lists an **A30 24GB at ₹38.88/hr** — cheaper than the L4 | New cheapest India-hosted GPU: **₹10,109/mo** business hours, down from ₹10,920 |
| **JarvisLabs was acquired by E2E Networks (2025)** — India's only listed pure-play GPU cloud. Datacenters now **Noida *and* Chennai** | Strengthens the India-residency story; no longer a single-datacenter dependency |
| **Sarvam AI found — an India-hosted per-token API billed in INR** | A genuinely new option: pay-per-question *without* sending data abroad. Was missing entirely from the last version. |

**The crossover point moved.** Previously per-token beat the India GPU below ~280 questions/day. With DeepInfra's price cut, that is now **~540 questions/day**.

---

## The core question: where does your data go?

This is the deciding factor, so it comes first.

| Option | Where your data is processed | Billed in | GST invoice |
|---|---|---|---|
| **A. Groq (current)** | 🔴 USA | USD | Reverse charge (OIDAR) |
| **B. Per-token API — foreign** (DeepInfra, Together) | 🔴 USA | USD | Reverse charge (OIDAR) |
| **C. Per-token API — India** (Sarvam AI) | 🟢 **India** | **INR** | ✅ Direct, clean ITC |
| **D. Rent a GPU — India** (JarvisLabs / E2E) | 🟢 **India (Noida / Chennai)** | **INR** | ✅ GSTIN on invoice, clean ITC |
| **E. Rent a GPU — foreign** (RunPod, Vast.ai, DeepInfra) | 🔴 USA / EU | USD | Reverse charge |
| **F. Cheap CPU-only server** (Contabo) | 🔴 Germany | EUR | Reverse charge |
| **G. Buy a machine for the office** | 🟢 **Your building** | — | Capital purchase |

If *"our data must not leave our control"* means **must not leave India**, only **C, D and G** qualify. That is now three options, not two — Sarvam is new.

**A note on GST that matters for a manufacturer:** JarvisLabs and Sarvam bill in rupees and issue a GST invoice against your GSTIN, so the 18% flows straight into input tax credit. Foreign USD APIs require reverse-charge self-assessment under OIDAR rules. The credit is claimable either way, but the Indian vendors are materially less paperwork for your accountant.

---

## The measured cost basis

Every per-token number below comes from one directly measured question, not an estimate.

> **One full report question = ~145,000 input + ~9,000 output tokens, across ~6 API calls.**
> Simple lookups (a plain count) are cheaper — 2–3 calls. The report figure is the safe number to budget with for a reporting tool.

**Why the number is that large, and why it matters:** 145,000 ÷ 6 calls ≈ **24,000 tokens per call** — which is exactly the size of the chatbot's instruction-and-schema prompt. In other words, **almost 100% of what you pay for is the same rulebook being re-sent six times per question.** Roughly 121,000 of those 145,000 tokens are pure repetition.

This single fact is the most important line in this document. It is what makes each question cost what it does, and it is fixable — see *"The number that changes everything."*

---

## What about Excel file uploads?

The chatbot already limits this deliberately, rather than sending the whole spreadsheet:

- Only the **first 50 rows** of any sheet, whatever the real file size
- Only the **first 40 columns**
- Plus a short numeric summary, not the raw data

So a 60-row attendance sheet and a 60,000-row sales export cost roughly the **same** to read — about **1,500–4,000 extra tokens per file**. At current DeepInfra pricing one attached file adds roughly **₹0.08 per question**. Even if every question carried a file, it is a couple of hundred rupees a month. **The 6-call loop, not the attachments, is what drives cost.** On the flat GPU options, files add nothing at all.

---

## Option A — Keep using Groq (what you have now)

**Not a live option anymore.** Two independent problems:

| Groq tier | Limit | Verdict |
|---|---|---|
| **Free** (no card) | **30 requests/min, 6,000 tokens/min** | ❌ The ~24K prompt exceeds the per-minute token cap **on the very first call.** Cannot run this chatbot at any volume. |
| **Developer** (free upgrade, card on file) | ~10× higher limits, 25% token discount | ✅ Works — but Groq now hosts only large models, priced far above the Qwen providers below. |

Groq also keeps retiring models — Llama-4-Scout, which this project started on, was discontinued in July 2026.

- **Data location:** 🔴 USA — same privacy profile as the Gemini demo that was rejected
- **Verdict:** Kept here only because it's where the project started.

**One free win worth taking regardless of what you choose:** Groq's Developer tier is a *free* upgrade (card on file, no minimum spend) and it does not count prompt-cache tokens toward rate limits. If you stay on Groq while testing, switch to Developer tier today.

---

## Option B — Per-token API, foreign (DeepInfra / Together)

Pay per question to a shared API. No servers to manage.

**Verified August 13, 2026** — model: **Qwen 3.5-9B** (the tested choice, 262K context):

| Provider | Input /1M | Output /1M | Per question | Data |
|---|---|---|---|---|
| **DeepInfra** ⭐ | **$0.04** | **$0.20** | **₹0.72** | 🔴 USA |
| Together AI | ~$0.055 | ~$0.275 | ~₹1.00 | 🔴 USA |

DeepInfra also runs ~2.2× faster on this model (205 tokens/sec vs Together's 92).

- **Cost:** Very cheap at low volume, but **climbs with usage and has no ceiling**
- **Data location:** 🔴 USA in every case. No India option for these models.
- **Known issue:** DeepInfra's marketing page promises "zero retention" but their Terms of Service says they "might store inputs and outputs for a limited time for debugging." Worth knowing if privacy is being presented as airtight to the client.
- **Rate limits:** No per-minute token wall — only 200 concurrent requests, far beyond one company's staff.

---

## Option C — Per-token API, India-hosted (Sarvam AI) ⭐ NEW

**What it is:** An Indian AI company running its own models on infrastructure inside India, billed in rupees, with a GST invoice. Pay-per-question like DeepInfra — but without the data leaving the country.

**Verified pricing (Aug 13, 2026), billed natively in ₹:**

| Model | Input /1M | **Cached input /1M** | Output /1M |
|---|---|---|---|
| **Sarvam 105B** | ₹29.28 | **₹10.98** | ₹73.20 |
| Gemma-4 31B (beta) | ₹36.60 | ₹13.73 | ₹91.50 |
| GLM 5.2 (beta) | ₹128.10 | ₹23.79 | ₹402.60 |

**Prompt caching changes this option completely.** Because ~121,000 of your 145,000 input tokens are the *same prompt repeated*, they qualify for the cached rate:

| | Per question |
|---|---|
| Sarvam 105B, no caching | ₹4.90 |
| **Sarvam 105B, with caching enabled** | **₹2.69** |

- **Data location:** 🟢 **India**
- **Billing:** INR, GST invoice, no reverse-charge paperwork
- **Model size:** 105B — considerably larger and likely smarter than Qwen 3.5-9B, which is part of why it costs more
- **Downside:** ~3.7× DeepInfra's price per question. Viable below ~145 questions/day; above that the India GPU is cheaper.
- **Must verify before committing:** Sarvam's docs do not explicitly state inference location or a data-retention policy. **Get this in writing** before presenting it to the client as an India-resident option.

---

## Option D — Rent an India-based GPU (JarvisLabs / E2E Networks) ⭐

**What it is:** A dedicated machine with a graphics card that runs only your chatbot's model. Nobody else's data touches it.

**Now stronger than in the last version:** JarvisLabs was **acquired by E2E Networks in 2025** — India's only publicly listed pure-play GPU cloud, with datacenters in Delhi NCR, Mumbai and Bengaluru. JarvisLabs itself runs **Noida and Chennai**, states *"your instances and their data stay in India,"* bills in rupees, and issues GST invoices against your GSTIN.

**Verified INR pricing (jarvislabs.ai/in, Aug 13, 2026):**

| GPU | VRAM | On-demand | Spot | Good for |
|---|---|---|---|---|
| **A30** ⭐ | 24GB | **₹38.88/hr** | ₹27.54/hr | A 7–9B model — the cheapest workable option |
| L4 | 24GB | ₹41.31/hr | ₹27.54/hr | Same class, slightly newer |
| A100 40GB | 40GB | ₹84.24/hr | ₹74.52/hr | A larger, smarter model |
| A100 80GB | 80GB | ₹140.94/hr | ₹84.24/hr | Largest models |

**Monthly cost (per-minute billing — you pay only while switched on):**

| Usage pattern | A30 24GB | L4 24GB | A100 40GB |
|---|---|---|---|
| **Business hours** (10 hrs × 26 days = 260 hrs) | **₹10,109** | ₹10,741 | ₹21,902 |
| Running 24/7 (730 hrs) | ₹28,382 | ₹30,156 | ₹61,495 |
| Business hours on **spot** (preemptible) | ₹7,160 | ₹7,160 | ₹19,375 |

**Add ~₹500–600/month for storage** (₹0.0130/GB/hr) to keep the model on disk while the instance is paused.

- **Data location:** 🟢 **India (Noida / Chennai)**
- **Fits the ₹10,000–15,000/month budget:** ✅ Yes, on A30 or L4 business-hours
- **Cost does not move with usage** — 100 questions/day or 2,000, the bill is identical
- **Setup required:** Someone must install and configure the model on the machine, and build an **auto on/off schedule** so it isn't billing overnight. One-time work on our side, not something JarvisLabs does for you.
- **Downside:** Rented, not owned. Slightly more upkeep than an API. First question each morning is slow while the model loads.

---

## Option E — Rent a GPU outside India

Listed for completeness — **not recommended** given the privacy requirement.

| Provider | GPU | Price/hr | Datacenter |
|---|---|---|---|
| RunPod (Community) | RTX 4090 24GB | $0.34/hr | USA/EU (varies) |
| DeepInfra dedicated | A100 80GB | $0.89/hr | USA |
| Vast.ai | RTX 4090 24GB | from $0.13/hr | ⚠️ **A marketplace of individual computer owners, not a company. Weakest privacy option in this document.** |

No privacy advantage over what was already rejected with Gemini.

---

## Option F — Cheap CPU-only server (Contabo VDS)

The original idea under discussion. **Verified: does not work for this use case.**

- **Price:** €94/month (~₹10,350) for the 16-core / 64GB box
- **The problem:** No graphics card. A single question with the ~8,000-word background context takes **30–70+ seconds just to start answering.** Too slow for a usable chatbot.
- **Verdict:** Same monthly cost as a real India-hosted GPU, but slower and hosted in Germany. **No reason to choose this.**

---

## Option G — Buy a machine for the office

The most literal answer to "our data must never leave our control."

- **Cost:** One-time **₹2–3 lakh** for a workstation with a suitable GPU, then only electricity (~₹500/month)
- **Data location:** 🟢 Physically inside your building
- **Breaks even against the A30 rental in ~20–25 months**
- **Downside:** If it breaks, it's your hardware to fix. No failover. Bigger upfront cost.

---

## Full pricing by usage pattern

Model priced: **Qwen 3.5-9B** on the per-token rows. Measured report question (145K in / 9K out), 26 working days/month.

| Option | 100 q/day | 500 q/day | **1,000 q/day** | 2,000 q/day | Data | Speed |
|---|---|---|---|---|---|---|
| **DeepInfra — Qwen 3.5-9B** | **₹1,884** | ₹9,420 | ₹18,840 | ₹37,680 | 🔴 USA | Fast |
| **Together AI — Qwen 3.5-9B** | ₹2,600 | ₹13,000 | ₹26,000 | ₹52,000 | 🔴 USA | Slower |
| **Sarvam 105B — India** (cached) | ₹6,994 | ₹34,970 | ₹69,940 | ₹1,39,880 | 🟢 **India** | Fast |
| **Sarvam 105B — India** (no cache) | ₹12,740 | ₹63,700 | ₹1,27,400 | ₹2,54,800 | 🟢 **India** | Fast |
| **JarvisLabs A30 — business hrs** ⭐ | **₹10,109** | **₹10,109** | **₹10,109** | **₹10,109** | 🟢 **India** | Fast |
| JarvisLabs L4 — business hrs | ₹10,741 | ₹10,741 | ₹10,741 | ₹10,741 | 🟢 **India** | Fast |
| JarvisLabs A30 — spot, business hrs | ₹7,160 | ₹7,160 | ₹7,160 | ₹7,160 | 🟢 **India** | Fast* |
| JarvisLabs A100 40GB — business hrs | ₹21,902 | ₹21,902 | ₹21,902 | ₹21,902 | 🟢 **India** | Fast |
| JarvisLabs A30 — 24/7 | ₹28,382 | ₹28,382 | ₹28,382 | ₹28,382 | 🟢 **India** | Fast |
| Contabo CPU box | ₹10,350 | ₹10,350 | ₹10,350 | ₹10,350 | 🔴 Germany | ❌ 30–70s+ |
| Own hardware | ₹2–3 lakh once, then ~₹500/mo | | | | 🟢 **Office** | Fast |
| Groq free tier | ❌ Not viable — 24K prompt exceeds the 6,000 tokens/minute cap on the first call | | | | 🔴 USA | — |

*Spot instances can be reclaimed with little notice — acceptable for testing, risky for a live client demo.

### Where the lines cross

| Comparison | Crossover point |
|---|---|
| DeepInfra vs. JarvisLabs A30 | **~540 questions/day** |
| Together AI vs. JarvisLabs A30 | ~389 questions/day |
| Sarvam (India) vs. JarvisLabs A30 (India) | **~145 questions/day** |

**How to read this:**

- **Below ~540 questions/day**, per-token is cheaper — but only DeepInfra, and it sends data to the USA.
- **Above ~540/day**, the flat India GPU wins, and per-token keeps climbing with no ceiling.
- **If data must stay in India**, the choice is Sarvam below ~145/day and the JarvisLabs A30 above it.
- **Flat options never move with usage.** One Excel file or five, 100 questions or 2,000 — same bill.

---

## The number that changes everything

Everything above assumes the **current** architecture: 6 calls, each re-sending a 24,000-token prompt. That prompt is the cost driver — not the model, not the host.

If the top 40–60 recurring questions become pre-written, verified query templates — so the AI does routing and narration on a ~1–2K prompt instead of re-deriving SQL from a 24K rulebook every time — the input drops roughly **12×**:

| After the architecture fix | 100 q/day | 500 q/day | 1,000 q/day | 2,000 q/day |
|---|---|---|---|---|
| **DeepInfra — Qwen 3.5-9B** | **₹595** | ₹2,977 | **₹5,954** | ₹11,908 |
| **Sarvam 105B — India** | ~₹1,900 | ~₹9,500 | ~₹19,000 | ~₹38,000 |

**At that point per-token beats the GPU up to roughly 1,700 questions/day**, and you would only pay for the India GPU to satisfy **privacy**, not cost.

**A second, cheaper lever: prompt caching.** Because ~121,000 of the 145,000 input tokens per question are literally the same text repeated, a provider that bills cached input at a discount cuts the bill without touching a line of application logic. Sarvam publishes a cached rate (₹10.98 vs ₹29.28 — a 62% discount, already applied in the tables above). **DeepInfra publishes cached rates on many models but has not confirmed one for Qwen 3.5-9B — worth asking them directly, as it would roughly halve the DeepInfra column for free.**

**Doing this in the wrong order** — buying the GPU now while keeping the 24K prompt — means paying ₹10,109/month to paper over something that costs nothing to fix.

---

## Recommendation

**The answer depends entirely on one thing: what "privacy" actually means to the client.** Ask this question before spending anything.

### If it means "our data must not leave India"

| Volume | Choose | Cost |
|---|---|---|
| Under ~145 questions/day | **Sarvam AI** (India-hosted API, INR billing, zero setup) | ~₹7,000/mo |
| Over ~145 questions/day | **JarvisLabs A30, business hours** (Noida/Chennai, INR, GST invoice) | **₹10,109/mo** |
| One-time cost preferred | **Own hardware in the office** | ₹2–3 lakh once |

Both India options fit the ₹10,000–15,000 budget. The A30 is the new best pick — cheaper than the L4 that was recommended previously.

### If it means "just not Google / not the big US AI companies"

**DeepInfra with Qwen 3.5-9B. ₹1,884/month at 100 questions/day.** Open-weight model, small independent vendor, no training on your data, a fraction of every other option. Not India-resident.

### Before spending on any of them

**Fix the prompt architecture.** It cuts cost 10–12×, improves accuracy, and makes every option on this list cheaper. Buy hosting to satisfy **privacy**, not to brute-force a cost problem that is really a prompt-size problem.

---

## What still needs deciding

- **The exact privacy requirement, in the client's own words.** "Not Google" and "not outside India" lead to different answers with a 5× cost difference between them. This is the single blocking question.
- **The real question volume.** Estimates in this document have ranged from 100/day to 2,000/day — a 20× spread that moves the recommendation across three different options. `cost_trace` already logs real token counts per turn; pull the actual average from AgentCost rather than estimating.
- **Get Sarvam's data-residency and retention policy in writing** before presenting it as an India-hosted option.
- **Ask DeepInfra whether Qwen 3.5-9B supports cached-input pricing.** If yes, their column roughly halves at no effort.
- **Which model** runs on whichever machine is picked — this affects answer quality, separate from hosting. Earlier free-model testing came back poor (most couldn't complete a real question; the one that did got 3 of 4 answers wrong). The next test needs a small paid-tier budget for a trustworthy read.
- **Switch the Groq account to Developer tier** — it's a free upgrade and the current free tier cannot run this chatbot at all.

---

*All prices re-verified directly on each provider's official pricing page on **August 13, 2026**, and converted at **$1 = ₹95.34**. Contabo's €94/month was carried forward from the Aug 11 check and not re-verified this round. Per-question cost is based on a directly measured report question: ~145,000 input + ~9,000 output tokens across ~6 API calls. Together AI's input/output split is derived from a published blended rate rather than a separately confirmed split. Prices and exchange rates change — re-confirm before final purchase.*
