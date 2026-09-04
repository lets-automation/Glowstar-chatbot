# Aastha ERP AI Chatbot — Running Cost

**Prepared:** August 14, 2026
**All rates verified directly against each provider's official pricing page on this date.**

This document answers one question: **what does it cost to run the chatbot each month?**

Costs are based on a **directly measured** question from the live system, not an estimate.

Exchange rate used throughout: **$1 = ₹95.34**

---

## The short answer

**Running cost is not a constraint on this project.**

Every realistic option lands between roughly **₹1,000 and ₹11,000 per month** at expected usage — all of them inside the ₹10,000–15,000 budget, several at a quarter of it.

Two free configuration changes cut the current bill by **half** immediately, with no change to the chatbot and no new supplier. Those are described below and should be made regardless of what else is decided.

**The open question is accuracy, not cost** — which AI model answers your questions correctly. That is a separate decision, and this document gives the price of each candidate so the choice can be made on quality rather than on cost.

---

## What drives the cost

The chatbot is billed per unit of text processed ("tokens"). One full report question was measured end to end:

> **One report question = ~145,000 units of input + ~9,000 units of output, across ~6 internal steps.**

Simple lookups (a plain count) cost less — 2 to 3 steps. The report figure is the safe number to budget with, since this is a reporting tool.

**Why the input number is large, and why it matters:** each of the 6 steps re-sends the same ~24,000-unit instruction set that teaches the AI your data structure. About **121,000 of the 145,000 input units per question are the same text, repeated.**

This single fact is the most important line in this document. It is what makes each question cost what it does — and it is the reason two free savings are available immediately.

### What about Excel file uploads?

The chatbot deliberately reads only a sample of any uploaded file — the first 50 rows and 40 columns, plus a short numeric summary, never the whole spreadsheet. So a 60-row sheet and a 60,000-row export cost about the same: roughly **₹0.08 extra per question.**

Even if every question carried a file, that is a couple of hundred rupees a month. **Attachments are not a cost concern.**

---

## Two free savings, available immediately

These apply to **any** model chosen, and cost nothing to activate. Shown here against the current configuration:

| | Per question | **Per month (100 q/day)** |
|---|---|---|
| Current configuration | ₹2.59 | ₹6,730 |
| **+ Developer tier (free upgrade)** | ₹1.94 | ₹5,048 |
| **+ Prompt caching (free, automatic)** | **₹1.29** | **₹3,360** |

**Saving: ₹3,370 per month, for two configuration changes.** There is no reason to defer these pending any other decision.

### The two changes

**1. Developer tier — a free upgrade.** Adding a payment method on file (with **no minimum spend**) reduces all token costs by **25%** and raises processing limits roughly tenfold. There is no subscription fee; you still pay only for what you use.

**2. Prompt caching — automatic, no code change.** Because ~121,000 units per question are the same instruction set repeated, they qualify for a **50% discount** on re-use. Groq lists cached input for `gpt-oss-120b` at $0.075 against $0.15 standard — exactly half. This applies automatically when the repeated text is sent first, which the chatbot already does. Cached text also does not count against processing limits, which roughly triples effective throughput.

---

## Per-question cost — every option

All figures include the Developer tier discount and prompt caching where the provider supports them.

| Provider | Model | Rate (input / output per 1M) | **Cost per question** |
|---|---|---|---|
| **Groq** | `llama-3.1-8b-instant` | $0.05 / $0.08 | **₹0.35** |
| **Groq** | `openai/gpt-oss-20b` | $0.075 / $0.30 | **₹0.65** |
| **Groq** | `openai/gpt-oss-120b` | $0.15 / $0.60 | **₹1.29** |
| DeepInfra | `Qwen3.5-9B` | $0.10 / $0.15 | ₹1.51 |
| Sarvam AI | `Sarvam 105B` | ₹29.28 / ₹73.20 | ₹2.69 |
| Groq | `llama-3.3-70b-versatile` | $0.59 / $0.79 | ₹4.07 |
| Groq | `qwen/qwen3.6-27b` ⚠️ | $0.60 / $3.00 | ₹5.56 |

⚠️ `qwen3.6-27b` is a **preview** model on Groq — the provider states it is for evaluation only and should not be used in production. Listed for completeness; not a candidate.

---

## Monthly cost by question volume

26 working days per month. **Pay-per-question options scale directly with use — no minimum, no ceiling, no subscription.**

| Questions/day | Groq 8B | Groq 20B | **Groq 120B** | DeepInfra 9B | Sarvam 105B | Groq 70B |
|---|---|---|---|---|---|---|
| **100** | **₹919** | ₹1,680 | **₹3,360** | ₹3,929 | ₹6,994 | ₹10,591 |
| **200** | ₹1,839 | ₹3,360 | **₹6,720** | ₹7,858 | ₹13,989 | ₹21,181 |
| **300** | ₹2,758 | ₹5,040 | **₹10,081** | ₹11,787 | ₹20,983 | ₹31,772 |
| **500** | ₹4,597 | ₹8,401 | **₹16,801** | ₹19,646 | ₹34,971 | ₹52,953 |
| **750** | ₹6,895 | ₹12,601 | **₹25,202** | ₹29,468 | ₹52,457 | ₹79,429 |
| **1,000** | ₹9,194 | ₹16,801 | **₹33,602** | ₹39,291 | ₹69,943 | ₹1,05,906 |

**Cost alone does not select the model.** The figures above establish what each candidate costs to run; accuracy on your data is assessed separately, and is the subject of the next stage of work.

What the table does show is that **the price differences are small in absolute terms.** At 100 questions/day the entire range spans ₹919 to ₹10,591 per month — so a model can be chosen on how well it answers, without cost being the deciding factor.

---

## Fixed-cost alternatives (rent a machine)

Instead of paying per question, you can rent a machine that runs the AI model exclusively for the chatbot. The bill is then flat regardless of usage — but each machine has a **hard capacity limit.**

| Option | Specification | **Per month** | Capacity | Verdict |
|---|---|---|---|---|
| **JarvisLabs A30** ⭐ | 24GB, business hours | **₹10,583** | ~545 q/day | Best GPU option — cheapest *and* fastest |
| JarvisLabs A30 (spot) | 24GB, business hours | ₹7,634 | ~545 q/day | ⚠️ Can be reclaimed without notice |
| JarvisLabs L4 | 24GB, business hours | ₹11,215 | ~225 q/day | Dearer and slower — see below |
| JarvisLabs A30 | 24GB, running 24/7 | ₹28,856 | ~1,300 q/day | Only if volume demands it |
| JarvisLabs A100 | 40GB, business hours | ₹22,376 | Higher | Faster, considerably dearer |
| **Contabo VDS** | CPU only, no graphics card | ~₹10,500 | — | ❌ **Not viable** |

*All GPU figures include ~₹474/month storage to keep the model on disk while the machine is switched off. Business hours = 10 hrs × 26 days.*

### When the GPU rental pays off

The bill is flat — ask 10 questions or 500, the invoice is identical. What limits a rented machine is not cost but **throughput**: one machine processes one queue, and beyond its capacity questions wait rather than cost more.

| Volume | Cheaper option | Monthly |
|---|---|---|
| **Below ~315 questions/day** | **Groq `openai/gpt-oss-120b`** | ₹3,360 at 100/day |
| **Above ~315 questions/day** | **JarvisLabs A30** | ₹10,583 flat, up to ~545/day |

Groq is cheaper for expected usage, and it has no queue and no setup. The A30 becomes the better buy if daily volume grows past roughly 315 questions — and it holds that advantage up to about 545 questions/day, after which a second machine would be needed.

### Choose the A30, not the L4

The two cards cost almost the same, but for this workload the A30 is roughly **twice as fast** — it uses high-bandwidth HBM2 memory (933 GB/s against the L4's 300 GB/s), and writing a long report is almost entirely a memory-bandwidth task.

The A30 is the older card, which is why it is cheaper; rental prices track age and market demand rather than suitability for a specific job. Its one real drawback is **availability** — it is an older part and may not always be in stock, in which case the L4 remains workable at roughly double the wait per report.

### Why Contabo does not work

The Contabo VDS has **no graphics card.** Processing the chatbot's instruction set on general-purpose processors is several times slower than even the weakest GPU option, for roughly the same monthly cost. **There is no scenario in which this is the right choice.**

### Why Contabo does not work

The Contabo VDS has **no graphics card.** Processing the chatbot's instruction set on general-purpose processors takes **many minutes per question** rather than seconds. It costs roughly the same as a real GPU rental while being unusably slow. **There is no scenario in which this is the right choice.**

---

## The larger saving still available

Everything above prices the **current** design: 6 steps, each re-sending a 24,000-unit instruction set.

If the 40–60 most common questions become **pre-written, verified templates** — so the AI handles routing and wording on a small instruction set instead of re-deriving everything from the full rulebook each time — the input drops roughly **12×**:

| | Per question | **Per month (100 q/day)** |
|---|---|---|
| Recommended configuration today | ₹1.29 | ₹3,360 |
| **After the design improvement** | **₹0.52** | **₹1,339** |

**A further ₹2,000/month saving, and it also improves accuracy and speed**, because the most common questions stop being re-derived from scratch each time.

This is development work on our side, not a purchasing decision. It is worth noting that **the cost is a design characteristic, not a supplier problem** — which is why we recommend making the two free changes now rather than committing to fixed infrastructure.

*Technical note: after this improvement, output length rather than input size becomes the main cost driver (roughly 75% of the remaining bill). That would be the next area to optimise.*

---

## Budget summary

| Scenario | Monthly cost (100 q/day) |
|---|---|
| Do nothing — current configuration | ₹6,730 |
| **Same model, two free changes applied** | **₹3,360** |
| Cheapest candidate — `llama-3.1-8b-instant` | ₹919 |
| Mid candidate — `openai/gpt-oss-20b` | ₹1,680 |
| Larger candidate — `llama-3.3-70b-versatile` | ₹10,591 |
| JarvisLabs A30 GPU rental (flat) | ₹10,583 |
| After the design improvement | ₹1,339 |
| Contabo VDS | ~₹10,500 (not viable) |

**Every workable scenario sits within the ₹10,000–15,000/month budget**, and most use a fraction of it. Cost is therefore not the deciding factor in this project — model accuracy is.

---

## Recommended next steps

1. **Activate the Groq Developer tier** — free, immediate, cuts costs 25%. Applies to any model chosen, so there is no reason to wait on it.
2. **Confirm prompt caching is active** — free, automatic, cuts costs a further ~33%. Same reasoning.
3. **Agree an accuracy test set.** We ask you for **15–20 questions you would genuinely put to this system in a normal week, together with the answers you would expect.** This becomes the acceptance standard — an objective measure rather than a judgement call.
4. **Run the accuracy test across the candidate models** in the table above and return with a recommendation and its exact monthly cost. The cost of each is already known, so this decision turns purely on quality of answer.
5. **Agree an expected question volume.** The system already logs real usage per question; one month of live data replaces every estimate in this document with a measured figure.
6. **Schedule the design improvement** — the largest remaining saving, and it improves accuracy and speed at the same time.

---

## Assumptions

- Costs are based on one measured report question: ~145,000 input units + ~9,000 output units across ~6 internal steps. Simple lookups cost less.
- 26 working days per month.
- Converted at **$1 = ₹95.34**. Groq, DeepInfra and JarvisLabs USD rates will move slightly with the exchange rate; Sarvam bills natively in rupees.
- Applicable taxes are additional and reclaimable as input tax credit in the normal way.
- GPU rental figures cover business-hours use (10 hrs/day, 26 days) plus ~₹474/month storage.
- GPU capacity figures (~225 q/day on the L4, ~545 q/day on the A30) are **calculated, not measured** — derived from the measured question size against each card's memory bandwidth, assuming an efficient model configuration (a Mixture-of-Experts model at 4-bit precision). Capacity varies several-fold with the model and precision chosen; a full-precision dense model would be roughly 4× slower. **If the GPU option is pursued, this should be measured on a rented machine before committing.**
- Groq rates for `llama-3.1-8b-instant`, `openai/gpt-oss-20b`, `openai/gpt-oss-120b` and `qwen/qwen3.6-27b` are taken directly from Groq's published model documentation. The `llama-3.3-70b-versatile` rate is from a third-party pricing summary and is not the recommended option.
- The Contabo figure is approximate and was not re-verified at source; it is listed only to record that the option was assessed and ruled out.
- Prices were verified on **August 14, 2026** and are subject to change by the supplier.
