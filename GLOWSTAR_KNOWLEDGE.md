# GlowStar Diamond — Industry & Company Knowledge Base

> **Purpose.** This document is the "20-year industry veteran" brain for the GlowStar chatbot
> (the text-to-SQL data analyst over the AasthaERP database). Feed it to the agent that
> maintains the chatbot: use it to (a) enrich `app/schema/glossary.py` (TERMS /
> GUJLISH_TERMS / VALUE_CODES), (b) extend the system prompt in `app/agent/tools.py`, and
> (c) answer identity questions ("who is GlowStar?", "what do you do?").
>
> **Confidence labels used throughout:**
> - ✅ **VERIFIED** — survived 3-vote adversarial fact-checking against primary sources (GIA, De Beers, Rapaport, IGI, HRD official pages; peer-reviewed Gems & Gemology).
> - 📄 **SOURCED** — from one good source (academic ethnography, BDB directory, company's own site) but not triple-verified.
> - 🧠 **TRADE KNOWLEDGE** — standard, uncontroversial industry knowledge; safe for conversation, confirm before using in SQL logic.
> - ❓ **CONFIRM WITH CLIENT** — plausible but unconfirmed; ask GlowStar staff before treating as fact.

---

## 1. THE COMPANY — GlowStar Diamond

> **CLIENT-CONFIRMED:** the chatbot's client is the GlowStar behind
> **`glowstaronline.com`** — the Surat one. Everything below describes this entity.

### 1.1 Who they are (📄 SOURCED — company sites, LinkedIn, BDB directory; identity confirmed by client)

- **GlowStar Diamond** is an Indian **manufacturer and exporter of cut & polished LOOSE
  NATURAL diamonds**, certified by **GIA, IGI and HRD**. It is *not* a jewelry brand and
  its public branding is explicitly "**GlowStar | Natural Diamonds**" (Instagram
  @glowstardiamond). Tagline: **"Selling Value Not Price."**
- **Classic Surat–Mumbai split** (their own site: "headquartered in Mumbai with a Surat
  manufacturing facility"): the cutting & polishing **factory is in Surat, Gujarat** —
  the operation this ERP/chatbot serves — with the sales/trading office at **CC-7070,
  Bharat Diamond Bourse (BDB), G-Block, Bandra Kurla Complex, Bandra-East, Mumbai 400051**.
  GlowStar is a listed **BDB member** (contact person on record: Keshavbhai Goti). The
  surname *Goti* is common in the Saurashtra-origin Surat diamond community.
- **Contacts (from their marketing site):** Tel 022-2627-7272/73, mobile +91 70410-04100,
  fax 022-4022-0199, email `info@glowstardiam.com`, Skype `glowstaronline`, QQ 1874697100
  (a Chinese messenger — consistent with their Hong Kong market presence).
- **Since when:** the company's own About text says it has imported & exported cut &
  polished diamonds **"since year 1995"**; its LinkedIn page and an IndiaMART listing say
  **founded/established 1987**. ❓ Ask the client which date to quote (likely: family firm
  1987, current trading form 1995).
- **Size:** LinkedIn self-reports **501–1,000 employees**; the IndiaMART (Mumbai) listing
  says 51–100. ❓ The larger figure likely includes Surat factory karigars; confirm.
- **Product range:** polished natural diamonds **0.18 ct to 3.00 ct**, clarity **IF through
  I3 including the trade grade SI3** (SI3 is a Rapaport/trade grade — GIA does not issue
  it), colors **D to M**, shapes **Round + fancies (Princess, Oval, Marquise, Pear, and
  other fancy shapes)**. Their own Facebook stock posts use the standard trade shorthand
  the chatbot must parse — e.g. "**0.40 ct D IF 3EX NON** GIA Certified Round" (= color D,
  clarity IF, triple-Excellent cut/polish/symmetry, no fluorescence).
- **Markets:** deals and markets in the four major centers — **India, Belgium (Antwerp),
  Hong Kong, USA**.
- **Web presence:** **`glowstaronline.com` is their login-gated online B2B stock portal**
  (no public marketing content — the whole site is a Login screen; their Facebook posts
  advertise certified stones "@ www.glowstaronline.com"). Marketing/company info lives on
  `glowstaronline.wordpress.com` ("GlowStar Diamond — Excellence In Diamonds") and
  `glowstardiam.com` (currently an "under construction" placeholder; content captured
  Mar 2025 on the Wayback Machine). Social: Instagram `@glowstardiamond`, Facebook
  "GlowStar Diamond" (Mumbai), LinkedIn "GLOWSTAR".

### 1.2 Disambiguation — do NOT confuse with (📄 SOURCED)

- **"Glow Star", Surat (IndiaMART)** — a *different* entity: a **partnership** firm
  (Gujarat GST registered July 2017) manufacturing **LAB-GROWN diamonds**, loose diamonds,
  rose cut/rustic diamonds and gemstones; self-reported turnover > ₹500 crore; contact
  "RAVI". Our GlowStar is a **natural**-diamond house — keep these separate.
- **"Glow Star Diamond", Mumbai (IndiaMART)** — est. 1987, 51–100 employees, contact
  "V Patel"; lists natural GIA-certified goods, non-certified goods, lab-created diamonds
  and a diamond **polishing service**. This one plausibly IS the same company as GlowStar
  (same 1987 date, same 0.18–3.00 ct range), listed under a variant name. ❓ Confirm.
- The client has confirmed the chatbot's company is the **glowstaronline.com** entity
  (Surat manufacturing). When any external listing conflicts with what client staff say,
  the client wins.

### 1.3 How the chatbot should use this

- Identity questions ("who are you?", "what does GlowStar do?") → answer from §1.1.
- The ERP the chatbot queries is a **Surat diamond-manufacturing** system (kapan → packet →
  planning → cutting → polishing → final), which matches GlowStar's Surat factory side.
- Never claim GlowStar sells lab-grown goods; its public identity is natural diamonds.

---

## 2. THE INDUSTRY — how a diamond gets to GlowStar

### 2.1 Rough supply (upstream)

- ✅ **De Beers sight system (today):** De Beers Group sells **~90% of its rough by value**
  through **Global Sightholder Sales (GSS)** to term-contract customers called
  **Sightholders**, at **Sights held 10 times a year in Botswana, Namibia and South
  Africa** (moved from London to Gaborone in 2013). Sightholders inspect pre-assembled
  rough allocations ("boxes") and decide whether to buy. Two customer classes exist:
  **Sightholders** (term contract) and **Accredited Buyers**. Roughly **10% of rough is
  sold via auctions** (run from Gaborone).
- ✅ **De Beers is no longer a monopoly:** it controlled ~80–85% of world rough
  distribution through the 20th century (~90% in the 1980s) but fell to ~63% by 2000 and
  **~30% by 2019**. Other rough sources: **Alrosa (Russia — under G7/EU sanctions since
  2022–24 🧠)**, Rio Tinto, Petra, Debswana; **tenders and auctions in Antwerp, Dubai
  (DMCC) and Botswana**; and the **open/secondary market**.
- ✅ **India & the sight system (history):** first **indigenous Indian sightholder 1964**;
  ~45 Indian sightholders (of ~160–170 worldwide) by the mid-1990s; then ~30% of India's
  rough came direct from De Beers, ~30% via Antwerp/Israel sightholders, rest open market.
  📄 In the late 1990s most Indian sightholders were **Palanpuri Banias (Jains)** and
  increasingly **Saurashtra Patels**, operating through Bombay head offices with branches
  in Antwerp, Hong Kong and New York. Today Indian firms are over half the (smaller)
  sightholder list. 🧠
- 🧠 **Kimberley Process (KPCS):** all rough imports/exports move under Kimberley Process
  certificates (anti-conflict-diamond regime); India is a founding participant and GJEPC
  administers it locally. Rough categories at assortment: **sawable, makeable, cleavage,
  near-gem, rejection/industrial, boart**.

### 2.2 Why Surat matters (history → today)

- ✅ **Origins:** the modern Indian industry was organizationally founded by **Palanpuri
  Jain** merchant families entering the polished import trade in **1909** (Palanpur,
  Gujarat). Around **1949** Palanpuri entrepreneurs moved into manufacturing and picked
  **Surat** (proximity to Bombay). First formal rough-import licenses under the
  government **Replenishment (REP) Scheme** in **1955**.
- 📄 Earlier roots: two Patidar brothers (Mavjivanwala) started cutting in Surat's **Vadi
  Faliya** in **1900** after returning from South Africa; pre-1940 the trade also ran
  through **Rangoon (Burma)** and WWII pushed Gujarati artisans back to Surat–Navsari.
- ✅ **The 1990s boom (historical figures — quote as history):** India polished ~**70% of
  the world's diamonds by weight** and ~35% by value, with a **near-monopoly on stones
  under 7 points**; **600,000–800,000 workers** across ~30,000 units (only ~5,500 big
  enough to call companies); labor ≈ 1/6 of Belgium/Israel; small stones polished for
  ~$1 each. Industry grew 82× by weight / 249× by value from 1966→1996.
- 📄 **1996 pipeline economics:** India imported **101 Mct of rough** (world mine output
  ≈ 111 Mct!), exported 18.88 Mct polished worth $4,235M (avg $224/ct — i.e. ~755 million
  stones averaging ~2.5 points); **polished yield 15.3–23.1% (avg ~18.7%)** of rough
  weight; ~3-month rough-to-polished turnaround.
- 📄 **Today:** ~**90% of the world's diamonds are cut & polished in Surat** (by pieces);
  Surat workforce ~**700,000–800,000**, drawn mostly from rural Saurashtra; ~10,000
  processing units in Gujarat. Exports grew from $28M (1966-67) to ~$18.7B (2019-20).
- 📄 **Markets in Surat:** the two historical street markets are **Mahidharpura** (old
  city) and **Mini Bazar (Varachha Road)**. The **Surat Diamond Bourse (SDB)** opened
  **December 2023** — ~6.7 million sq ft, called the world's largest office building.
  Mumbai's **Bharat Diamond Bourse (BDB, BKC)** remains the main export/trading hub —
  GlowStar's own trading office is there.

### 2.3 The manufacturing pipeline (Surat factory floor)

Stage-by-stage — this is what the ERP's `Process` column tracks
(`IN Stock → Weight Scale → Marker → Laser → Galaxy → Blocking → Vision 360 → Polish
Checker → MFG-1/2 → OUT Stock`):

1. **Assortment / sorting (rough)** — rough parcels (**kapans**) are sorted by size,
   shape, quality, color into processing lots. 🧠
2. **Planning / marking** — deciding how to cut each rough stone to maximize value.
   📄 The **Sarine Galaxy** inclusion scanner is standard in all major Surat factories for
   goods above ~**0.30 ct** (melee is still planned by eye). Planning software
   (Sarine **DiaExpert / Advisor**, also Lexus/OGI 🧠) proposes solutions; modern software
   plans 10–15 possible polished outcomes vs 1–2 historically. The **Marker** marks the
   saw line. The ERP's "Galaxy" process = Galaxy scanning; "Marker" = marking.
3. **Cleaving / sawing** — splitting the rough along the plan. 📄 **Laser sawing has
   replaced mechanical sawing** in most serious operations (ERP process "Laser").
   Green-laser systems (Sarine **Quazer** 📄; Synova water-jet-guided lasers with
   micro-machining centers in Surat & Mumbai 📄) cut with minimal weight loss; a stone
   can now be cut and polished in a single day.
4. **Bruting / girdling (blocking the shape)** — grinding two diamonds against each other
   or laser-bruting to round the girdle outline. ERP "Blocking" = putting the first main
   facets / basic shape on the stone. 🧠
5. **Polishing (faceting)** — on the **ghanti** (Gujarati: the cast-iron polishing wheel,
   called **scaife** in the West) charged with diamond-powder paste; typically several
   karigars sit around one wheel. 📄 The classic division of polishing labour in Surat
   (each a separate piece-rated task — these names appear in the ERP labour tables'
   world):
   - **Table** ("tablework") — the single big top facet.
   - **Girdle rounding**.
   - **Taliya / talia** — the **bottom (pavilion) facets** (24 of them).
   - **Athpel** — the **top 8 main crown facets** (*ath* = eight, *pel* = facet).
   - **Mathala** — the **top 24 crown facets** (upper girdle + star work).
   A round brilliant has **57–58 facets** (58 with culet). 📄
6. **4P / final checking** — checking the "4 P's" of make — **Proportion, Polish,
   Symmetry (and the overall finish)** — plus clarity/color re-check before the stone
   leaves ("Vision 360", "Polish Checker" in the ERP; big factories historically had
   separate sections for cutting, bruting, polishing, **checking and assorting** 📄).
7. **Assortment (polished) & grading** — stones are assorted into parcels by size/color/
   clarity; certifiable goods (typically ≥ 0.18–0.30 ct) go to **GIA / IGI / HRD** labs;
   melee is sold in parcels by sieve size. 🧠
8. **Sale / export** — via the Mumbai (BDB) office, on RapNet, at trade shows, or on
   jangad to trusted buyers (see §4). 🧠

📄 Training a competent commercial cutter takes ~6–12 months; cutters trusted with big
stones need years. Sarine's **DiaMension HD** is used for cut/symmetry measurement (Sarine
claims GIA approval for symmetry grading).

### 2.4 Lab-grown diamonds (LGD) — 🧠 TRADE KNOWLEDGE

- Two growth methods: **HPHT** (high pressure high temperature — metal-flux press;
  historically yellowish, now good colors) and **CVD** (chemical vapor deposition —
  methane plasma grows type-IIa plates; often post-treated by HPHT to improve color).
- **Surat/Gujarat is the world's dominant LGD cutting hub and a major growing hub**;
  LGD prices collapsed steeply from ~2022 onward, pressuring margins industry-wide.
- Detection: labs use DiamondView/FTIR/spectroscopy; **IGI is the dominant LGD grading
  lab** and ✅ auto-inscribes every lab-grown stone's girdle as lab-grown (natural stones
  are inscribed only on request). ✅ HRD reports state natural vs laboratory-grown in
  clear wording on the cover.
- **GlowStar sells NATURAL diamonds** — LGD matters to the chatbot only as industry
  context and to avoid confusing the similarly-named Surat LGD firm (§1.2).

---

## 3. GRADING — the full vocabulary

### 3.1 The 4Cs (✅ VERIFIED against GIA)

- **GIA created the 4Cs** (Color, Clarity, Cut, Carat weight) — Robert Shipley coined
  "4Cs" in the early 1940s; Richard Liddicoat's team built the D–Z color and FL–I3 clarity
  scales in **1953**; first grading reports **1955**. It is the universal trade language.

**Carat** ✅ — metric carat = **0.2 g exactly = 100 points** ("a 25-pointer" = 0.25 ct).
Scales read to 5 decimals; reports round to 2. 🧠 *Magic sizes* (0.30, 0.50, 0.70, 0.90,
1.00, 1.50, 2.00 ct) carry disproportionate price jumps — the Rapaport grid changes
brackets there. In Surat small goods are counted in **"cents"** (= points): "below 5
cents" = under 0.05 ct. 📄

**Color** ✅ — **D to Z, 23 grades, five categories**: Colorless (D–F), Near Colorless
(G–J), Faint (K–M), Very Light (N–R), Light (S–Z). Graded table-down against calibrated
**master stones**. ✅ IGI: multiple graders give independent opinions; grade set by
consensus. ✅ HRD pairs letters with descriptive names (D = "Exceptional White +", … Z =
"Tinted Colour"). Beyond Z = **fancy color** grades (Faint → Fancy Light → Fancy → Fancy
Intense → Fancy Vivid/Deep/Dark) 🧠. *The ERP's `Color` column stores D…N codes.*

**Clarity** ✅ — 11 grades, six categories, judged at **10× magnification** on five
factors: **number, size, relief, nature, location**:
`FL, IF, VVS1, VVS2, VS1, VS2, SI1, SI2, I1, I2, I3`
- FL: no inclusions or blemishes; IF: blemishes only; VVS: very hard even for a skilled
  grader; VS: minor, seen with effort; SI: noticeable; I1–I3: obvious, may affect
  transparency/brilliance/durability. **Inclusions** = internal & surface-reaching;
  **blemishes** = external only. Most store-sold goods are VS–SI.
- 🧠 **SI3** — a **Rapaport/EGL trade grade** between SI2 and I1; GIA/IGI/HRD do not issue
  it, but GlowStar's own range list uses it (§1.1) and dealers price it.
- ✅ **HRD nomenclature differs:** top grade **LC (Loupe Clean)** instead of FL/IF, bottom
  **P1, P2, P3 ("Piqué")** instead of I1–I3. Full HRD scale:
  `LC, VVS1, VVS2, VS1, VS2, SI1, SI2, P1, P2, P3`. Essential when reading European certs.
- *The ERP stores clarity in a column named **`Purity`** — never look for a "Clarity"
  column.*

**Cut** ✅ — GIA scale (2005): **Excellent, Very Good, Good, Fair, Poor** — applied as an
overall grade only to standard **round brilliants** D–Z. **GIA has no "Ideal" grade.**
✅ IGI's top round grade is **"Excellent-Ideal"**; IGI fancy-shape cut grading is optional
(Excellent→Poor, four steps: polish+symmetry, proportions, craftsmanship checks like
bow-tie/girdle, light return; needs ≥ Very Good polish & symmetry to be an Excellent
candidate). ✅ HRD splits cut into three sub-grades — **proportions, polish, symmetry** —
each Excellent/Very Good/Good/Fair.
- 🧠 Cut anatomy vocabulary: table %, total depth %, crown angle/height, pavilion
  angle/depth, girdle (thin→thick), culet, star facets, upper/lower girdle (halves),
  brillianteering, hearts & arrows, bow-tie (fancies), fish-eye, nail-head.
- *ERP `Cut/Polish/Symmetry` codes: EX, VG, GD, FR — "3EX" (triple excellent) is the
  premium make* 🧠.

**Fluorescence** — how the stone glows under long-wave UV; grades **None, Faint, Medium,
Strong, Very Strong** (usually blue). ✅ IGI: ~35% of diamonds fluoresce; strength and
color are recorded. 🧠 Strong blue fluorescence usually discounts D–H goods (can look
hazy/"milky") but can help lower colors face whiter. *ERP columns are misspelled
`Florecent`/`Florocent`; values NON/FNT/MED/STG/VST.*

### 3.2 Shapes (ERP codes ↔ trade names) 🧠

RD=Round (brilliant), PR=Princess, EM=Emerald (step cut), SQEM=Square Emerald/Asscher,
OV=Oval, MQ=Marquise, PS=Pear, HR=Heart, CU=Cushion, RAD=Radiant, BG=Baguette,
TRI=Trillion; plus fancy/special variants (F.xx / S.xx). Everything non-round is a
"**fancy shape**". Rose cut and polki are old-style cuts used in Indian jewelry.

### 3.3 The labs (🧠 unless marked)

- **GIA** (Gemological Institute of America) — inventor of the system, most authoritative
  for natural goods. ✅
- **IGI** (International Gemological Institute) — dominant for lab-grown and very strong
  in India; ISO 17025-accredited for natural & LGD grading ✅; HQ historically Antwerp,
  large labs in Mumbai & Surat 🧠.
- **HRD Antwerp** — the Belgian lab (Hoge Raad voor Diamant / Diamond High Council);
  European nomenclature (LC, Piqué) ✅.
- GlowStar certifies with all three (§1.1). Certifiable = usually 0.18 ct up 🧠 — exactly
  GlowStar's stated bottom size.

---

## 4. TRADING PRACTICES & PRICING

### 4.1 Rapaport ("Rap") — ✅ VERIFIED

- The **Rapaport Price List** is the industry's primary market-value reference. It is
  **Rapaport's opinion of HIGH CASH ASKING prices** for well-cut white diamonds — **not
  transaction prices**. Dealers therefore quote **discounts off list**, using the word
  **"back"**: *"20 back"* = 20% below the Rap price for that size/color/clarity cell.
  Typical dealer discounts run 10–40%; scarce goods can trade at a **premium** over list.
- Mechanics: published **weekly, Thursday midnight New York time**; covers **Round and
  Pear only** (the Pear sheet benchmarks all other fancy shapes); grid spans
  **0.01–10.99 ct**, colors **D–M**, clarities **IF–I3**; prices are **USD in hundreds
  per carat** (grid "28" = $2,800/ct). Four tables per shape by carat bracket; big jumps
  at the size brackets ("magic numbers").
- The list prices only 3 of the 4 Cs — **cut, polish, symmetry and fluorescence are NOT
  in the grid**; dealers adjust for them on top (e.g. in the separate monthly **Parcel
  Price List** for non-certified rounds, Excellent cut ≈ +10%, Good ≈ −10% vs the
  Very Good base).
- **RapNet** is the companion online trading network where members list goods at
  %-back-of-Rap asking prices. 🧠

### 4.2 Jangad / memo (📄 SOURCED + ERP-critical)

- **Jangad** = goods given **on approval / entrustment / consignment** — a trust-based
  handover that is **NOT a sale**: the receiver may sell onward or return the goods; title
  stays with the owner until confirmed sold. The accompanying document is the **jangad
  note** ("acknowledgement of entrustment") recording quantity and value. Western
  equivalent: "**on memo**".
- *ERP: `tblJangadPackets.IsReceived = 0` → still out on jangad ("pending"); 1 → returned.
  A jangad return is goods coming BACK — never report it as a sale.*

### 4.3 Brokers, couriers, settlement

- **Dalal** = broker/middleman (Gujarati/Hindi); **dalali** = brokerage commission —
  conventionally ~1% in the polished trade ❓(confirm rate with client). Deals are done on
  word + handshake; the community system enforces trust. 🧠
- **Angadia** 📄 = Gujarat-origin trusted-courier network physically carrying diamonds,
  cash and valuables between Surat and Mumbai (and city offices like Opera House / Zaveri
  Bazaar). Legal in India; estimated ₹70,000 crore–₹1 trillion of goods moved yearly;
  a dedicated category serves the diamond trade (rough & polished parcels Surat ⇄ Mumbai
  export houses). Historically horse carriages to Mumbai Central; now police-escorted.
- 🧠 Settlement culture: prices in USD (converted at the day's rate), payment terms in
  days (COD / 30 / 60 / 120 days), post-dated cheques common; **Diwali** is the trade's
  year-end (factories close ~2–4 weeks; "Diwali vacation" shows up in attendance data ❓).
- 📄 **Baki** — historical Surat term for the **advance money** owners paid to bind
  karigars to a workshop (late-1970s Rs 400–500 → Rs 5,000–25,000), which became a
  debt-bondage scandal and collapsed in the late 1980s. NOTE: in everyday Gujarati
  **"baki" simply means "remaining/balance/outstanding"** — in ERP questions, "baki"
  almost always means the *pending/outstanding amount or goods*, not the old advance
  system.

### 4.4 Labour economics (📄 historical; ERP-relevant)

- Polishing is **piece-rated per stone and per task** (table / girdle / taliya / athpel /
  mathala had separate rates — 1990s figures: table Rs 1.50–2 per stone at 150–200
  stones/day; pavilion ("bottom") Rs 6–10; athpel Rs 4–6). *The ERP mirrors exactly this:
  `tblPointRateLabour` (rate **per point** of weight), `tblLabourRate` (per process/stage),
  incentives and bonuses on top.*
- The workforce and many owners come overwhelmingly from the **Saurashtra (Kanbi
  Leva/Kadva) Patel** community 📄; traders historically Palanpuri Jain. Workers are
  **karigars**; owners are **seth/shethiya** 🧠.

---

## 5. INDUSTRY BODIES

- **GJEPC** — Gem & Jewellery Export Promotion Council, est. **1966** under the Ministry
  of Commerce 📄; the apex export body — runs IIJS shows, administers Kimberley Process
  locally, publishes trade statistics. 🧠
- **BDB** — Bharat Diamond Bourse, BKC Mumbai — the world's largest diamond bourse
  complex and India's export hub; ~2,500 member offices 🧠. **GlowStar sits in CC-7070.** 📄
- **SDB** — Surat Diamond Bourse, opened **Dec 2023**, ~6.7M sq ft, world's largest
  office building 📄; intended to move trading to Surat (adoption still ramping 🧠).
- **SDA** — Surat Diamond Association (local trade body) 🧠. **WFDB** — World Federation
  of Diamond Bourses (BDB & SDB are members) 🧠.
- Mines/miners worth knowing: De Beers (+Debswana JV in Botswana), **Alrosa** (Russia,
  sanctioned), Rio Tinto (Argyle closed 2020 — was the pink/small-goods source), Petra
  (Cullinan). ~20 Indian firms, incl. sightholders, now also cut in **Botswana**
  (beneficiation). 📄

---

## 6. GUJARATI / HINGLISH DIAMOND LEXICON

> These are **meaning** words to translate user intent — never match them against data
> values or names. Extends `GUJLISH_TERMS` in `app/schema/glossary.py` (whose existing
> entries — sauthi vadhare, ketla, karigar, maal, atyare, etc. — remain correct).

### 6.1 Manufacturing-floor terms (📄 SOURCED from Surat ethnography/studies unless noted)

| Term | Meaning |
|---|---|
| **hira** | diamond (હીરા). "Hira bazar" = diamond market. 🧠 |
| **hira karigar / karigar** | diamond cutter-polisher / skilled worker. 📄 |
| **ghanti** | the polishing wheel (steel/cast-iron, diamond-paste-charged, motor-driven; several karigars sit around one). Western term: *scaife*. 📄 |
| **hiraghasu** | "diamond-grinder" — old derogatory nickname Surtis used for migrant Saurashtrian polishers. 📄 (recognize, don't use) |
| **kapan** | a lot/parcel of rough processed as one batch (already the ERP's core unit). Existing glossary ✅ |
| **packet** | sub-parcel of a kapan tracked through the factory. Existing glossary ✅ |
| **table / tablework** | polishing the single top facet (a distinct paid task). 📄 |
| **taliya / talia** | polishing the **pavilion (bottom) facets** (~24). *Taliyu* = bottom. 📄 |
| **mathala** | polishing the **upper crown facets** (~24). *Mathu* = head/top. 📄 |
| **athpel** | polishing the **8 main crown facets** (*ath*=8, *pel*=facet). 📄 |
| **pel** | a facet / facet-polishing pass. 📄 (from athpel) |
| **ghat** | shape/form of the stone; "ghat aapvo" = to give shape (bruting/blocking). ❓ |
| **cent** | 1/100 carat = a point. "5 cent no nang" = a 5-pointer. 📄 |
| **nang** | a piece/stone — the counting word for diamonds ("ketla nang?" = how many stones?). 🧠 |
| **vajan** | weight. 🧠 |
| **kacho maal / rough** | rough/unfinished goods; **tayyar maal** = finished/polished goods. 🧠 |
| **bhangar** | scrap/junk/rejection material (ERP: Junk). 🧠 |
| **daag** | spot → an inclusion; "kala daag" = black inclusion. ❓ |
| **paani** | "water" = luster/limpidity of a gem (old trade idiom, e.g. "first water"). 🧠 |
| **majuri** | labour charge / piece-rate wages (ERP: labour rate/amount). 🧠 |
| **pagar** | salary/wages. 🧠 |
| **haajar / gerhajar** | present / absent (attendance questions). 🧠 |
| **raja** | leave / holiday. 🧠 |
| **sagdi, mandvi, ratti** | ❓ unverified as Surat diamond-floor terms — *ratti* is a traditional S-Asian gem weight (~0.6075 ct? used for astrological gems, not diamonds); ask the client before mapping. |

### 6.2 Trading terms

| Term | Meaning |
|---|---|
| **jangad** | goods on approval/entrustment (NOT a sale); jangad note = the entrustment document. 📄 ERP-critical (see §4.2). |
| **dalal / dalali** | broker / brokerage commission. 🧠 |
| **angadia** | trusted courier carrying diamond parcels & cash (Surat ⇄ Mumbai). 📄 |
| **baki** | outstanding / remaining / balance (everyday sense); historically the worker-advance system (§4.3). 📄 |
| **udhar** | on credit; **rokad** = cash. 🧠 |
| **bhav** | price/rate ("aaj no bhav" = today's rate). 🧠 |
| **back** | % discount off the Rapaport list ("20 back"). ✅ |
| **Rap / Rapo** | the Rapaport price list. ✅/🧠 |
| **seth / shethiya** | owner/boss/proprietor. 🧠 |
| **vepari** | trader/merchant. 🧠 |
| **hisab** | account/reckoning ("hisab aapo" = give the account/summary). 🧠 |
| **chukvani** | payment/settlement. 🧠 |
| **sight / sightholder** | De Beers term-contract rough buyer (used as-is in Gujlish). ✅ |
| **polki** | flat, uncut/rose-cut diamond used in jadau jewelry (jewelry-side term). 🧠 |

### 6.3 Question-word Gujlish (extends the existing glossary set) 🧠

| Phrase | Intent |
|---|---|
| su / shu | what |
| kem | why / how ("kem che" = how are you) |
| kyare | when (time filter) |
| kone / kona | who / whose (employee lookup) |
| ketla nang | how many stones (COUNT) |
| kul | total (SUM) |
| sarasari | average (AVG) |
| aaje / kaale | today / yesterday-or-tomorrow (context) |
| gaya mahine / aa mahine | last month / this month |
| aa varshe / gaya varshe | this year / last year |
| badha / badhu | all / everything |
| navu / junu | new / old |
| motu / nanu | big / small |
| vadhyu / ghatyu | increased / decreased |
| chalu | active/running (IsActive=1) |
| band | closed/stopped/inactive |
| kharab | bad / damaged (→ damage report, repair) |
| tutela | broken (→ damage/repair) |
| baki che | is pending/outstanding (jangad IsReceived=0, dues) |

---

## 7. READY-TO-PASTE SYSTEM-PROMPT ADDITION

Condensed block for `RULES` in `app/agent/tools.py` (or a new `COMPANY_CONTEXT` constant —
keep it out of the per-question schema budget if tokens are tight):

```text
ABOUT THE COMPANY:
You are the data assistant of GlowStar Diamond ("Selling Value Not Price") — an Indian
manufacturer & exporter of cut & polished LOOSE NATURAL diamonds (GIA / IGI / HRD
certified), in the trade since the 1990s. Factory: Surat, Gujarat (this ERP tracks that
factory). Trading office: CC-7070, Bharat Diamond Bourse, BKC, Mumbai 400051. Online
stock portal: glowstaronline.com. Range: 0.18–3.00 ct, D–M color, IF–I3 clarity (incl.
trade grade SI3), Round + fancy shapes. Markets: India, Belgium, Hong Kong, USA.
GlowStar deals in NATURAL diamonds (not lab-grown, not jewelry).

INDUSTRY MENTAL MODEL:
Rough (kapan) is bought (De Beers sights / tenders / open market), planned on Sarine
Galaxy-class scanners, laser-sawn, blocked/bruted, polished on the ghanti wheel as
piece-rated tasks (table, girdle, taliya=pavilion facets, athpel=8 crown facets,
mathala=upper crown facets), checked (proportion/polish/symmetry), assorted, certified
(GIA/IGI/HRD), and sold from Mumbai — sometimes sent out on JANGAD (approval/entrustment,
NOT a sale; jangad return = goods coming back). Prices reference the weekly Rapaport
list; dealers quote "% back" (discount) off Rap. 1 carat = 0.2 g = 100 points ("cents").
Color D–Z (D best); clarity FL,IF,VVS1-2,VS1-2,SI1-2(,SI3 trade),I1-3; cut/polish/
symmetry EX/VG/GD/FR; fluorescence NON/FNT/MED/STG/VST (blue glow under UV; column is
misspelled 'Florecent'/'Florocent'). Workers (karigars) are paid per point/stone per
task; attendance, incentives and damage are tracked in this ERP. Diwali is the trade's
year-end holiday season.
```

---

## 8. HOW TO APPLY THIS TO THE CODEBASE (for the maintaining agent)

1. **`app/schema/glossary.py` → GUJLISH_TERMS:** merge §6 tables (keep the existing
   entries; add new ones with the same "translate intent, don't match as names" rule).
   Mark ❓ items `"status": "verify"`.
2. **`app/schema/glossary.py` → TERMS:** add: Ghanti, Taliya, Mathala, Athpel, Cent/Nang,
   Dalal, Angadia, Rapaport/Back, SI3, 4P checking — short one-liners from §2.3/§4.
3. **`app/agent/tools.py` → RULES:** append the §7 block (or gate it behind
   identity/industry questions to save tokens for pure SQL questions).
4. **Do NOT change SQL behavior** from this document alone — everything that touches
   query logic (tables, joins, value codes) stays governed by the existing glossary,
   which was validated against the real database.
5. Items marked ❓ → collect into a client-questions list (dates 1987 vs 1995; employee
   count; dalali %; sagdi/mandvi/ratti; whether "ghat" is used on their floor; Diwali
   closure handling in attendance).

## 9. PRIMARY SOURCES

- Gems & Gemology (GIA, Spring 1998): *The Rise to Prominence of the Modern Diamond
  Cutting Industry in India* — history & 1990s economics (✅ claims).
- De Beers Group — debeersgroup.com/our-business/diamond-trading; gss.debeersgroup.com (✅).
- Rapaport/RapNet help center — Introduction to the Rapaport Price List (✅).
- GIA 4Cs pages — 4cs.gia.edu (color/clarity/cut scales, definitions) (✅).
- IGI — igi.org/diamond-grading-process (+ cut-grading, fancy-shape PDF) (✅).
- HRD Antwerp — hrdantwerp.com/4cs (✅).
- Miranda Engelshoven, *Diamonds and Patels: a report on the diamond industry of Surat*
  (academic ethnography) — ghanti, karigar, baki, markets, piece rates, sight history (📄).
- *Assessing the Work Environment of Surat Diamond Polishing Industry* (occupational
  study) — tablework/girdle/talia/athpel/mathala task names (📄).
- Wikipedia: Angadia; jangad etymology & trade-usage sources (📄).
- BDB member directory (bdbindia.org/member/glowstar), GlowStar LinkedIn,
  glowstardiam.com, glowstaronline.com, IndiaMART listings, @glowstardiamond (📄 company).
- Trade press: naturaldiamonds.com (Surat), nationaljeweler.com (technology journey),
  Sarine blog (machines) (📄).
