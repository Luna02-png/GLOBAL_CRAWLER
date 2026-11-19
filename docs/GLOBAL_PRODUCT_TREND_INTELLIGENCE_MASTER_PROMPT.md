# GLOBAL PRODUCT TREND INTELLIGENCE
## Master Prompt V3.2 — Full Specification for Codex

> **Instructions to Codex:** Treat this document as the complete, consolidated product and implementation specification. Build and test a functioning application, not a mockup. Do not silently drop requirements. Preserve existing repository code and data if a project already exists. Work incrementally and report objectively which integrations are working, restricted, or pending configuration.

---

## 1. Mission and operating principles

You are a senior software architect, full-stack engineer, data engineer, web research specialist, and market-intelligence analyst. Build a production-oriented **Global Product Trend Intelligence** application for discovering, verifying, analyzing, tracking, and exporting product-level trends across user-selected industries and geographic markets.

The application must help users:

1. Find products **currently popular** in a selected market.
2. Find products **just beginning to rise**, before they become mainstream.
3. Track **upcoming launches, leaks, and rumors** with clear uncertainty labels.
4. Compare product trends across **multiple countries and regions**.
5. Identify **cross-market business opportunities**, without assuming popularity in one country guarantees demand in another.
6. Find the **best product information page** for each product (official product page, detailed article/review, release announcement, or retailer listing); retail purchase links are optional, separate results.
7. Collect **original reference URLs** from articles, social posts, official announcements, retail listings, and other permitted sources.
8. Export a **flat, Google Sheets-compatible product table** with individually copyable names, image URLs, product links, and reference links.
9. Control precisely **what, where, when, and how deeply** to scan.
10. Preserve historical observations and show **what changed since the previous scan**.

### Absolute priorities

**Data accuracy > canonical product matching > most informative relevant product page URL > verifiable source evidence > Google Sheets usability > optional shopping links > scan reliability > history and scoring > presentation.**

Never fabricate a product, SKU, image, link, publication date, engagement metric, release date, trend score input, or historical time-series point. Distinguish **not observed**, **unknown**, **unavailable**, and **verified absent**. Do not present test fixtures as live discoveries.

The first implementation must work with at least one real, legally accessible source; a beautiful dashboard backed only by mock data is not acceptable.

---

## 2. Product structure and navigation

Build a single application with **five primary research modules** and shared utility pages.

### Five primary modules

1. **Trend Dashboard** — Products already trending; market, brand, and category overview.
2. **Product Research Sheet** — The main spreadsheet-like research interface and export workspace.
3. **Upcoming Releases & Rumors** — Future launches, rumors, leaks, confirmations, and date revisions.
4. **Trend Opportunity Finder** — Compare source and target markets; detect gaps and early opportunities.
5. **Early Trend Radar** — Detect velocity, acceleration, and product lifecycle transitions before mainstream popularity.

### Shared utility pages / panels

- **Smart Scan Manager** — User-defined presets, multi-category selection, schedules, priorities, progress, history, and resource limits.
- **Industry & Category Manager** — Dynamic product taxonomy; custom industries and multilingual aliases.
- **Source Manager** — Source registry, credentials, permitted adapters, errors, and health.
- **Product Link Finder** — Product-level and bulk research-page discovery, best information page selection, and optional shopping links.
- **Saved Lists** — Early Trend Watchlist and Opportunity Shortlist.
- **Settings** — Markets, scoring profiles, export preferences, scheduler timezone, system limits.
- **What's New Since Last Scan** — Unified changes, filters, and links to affected records.

The five research modules must read the same canonical product database rather than keeping disconnected product copies.

---

## 3. User-defined industry, category, and product taxonomy

The entire taxonomy must be editable in the application and persisted in the database:

**Industry → Category → Subcategory → Product**

Initial **example industries**, not fixed restrictions:

- Fashion & Footwear — Sneakers, Air Jordan, Nike, Adidas, ASICS, New Balance, clothing, hoodies, jackets, jerseys, denim, bags, sneakerboots, accessories.
- Electronics & Technology — Smartphones, headphones, earbuds, gaming devices, PC accessories, AI gadgets, smart home.
- Beauty & Personal Care — Skincare, makeup, fragrance, haircare.
- Home & Living — Furniture, decor, kitchen, household goods.
- Sports & Outdoor — Running, cycling, fitness, camping, sports gear.
- Toys & Collectibles — LEGO, figures, trading cards, limited editions.
- Automotive Accessories — Car and motorcycle accessories, automotive tech.
- Lifestyle & Pet — Travel, pets, everyday lifestyle products.
- Food & Beverage — Snacks, coffee, packaged products, food trends.
- Other / User-created industries.

Requirements:

- Create, edit, rename, deactivate, delete, and merge taxonomy nodes with safe migration rules.
- Select **one, multiple, a whole group, or all** industries/categories/subcategories in a scan.
- Category search, checkboxes, select-all/clear-group, nested selections, and user-defined category groupings.
- Custom keywords, excluded keywords, local-language keywords, product aliases, brand mappings, and preferred sources.
- Multiple categories may reference the **same canonical product**; use many-to-many associations. Do **not** create duplicate products when the user selects overlapping categories.
- Industry-specific product attributes must be configurable; fashion colorways/sizes, technology model/storage/connectivity, collectible edition, beauty size/variant, etc.
- Preserve all previously collected products when modifying scan presets or category configuration.

### Distinguish scan selection from display filtering

**Scan Category Selection** determines what to collect. **Table Category Filter** determines what already collected data to display. Changing a table filter must **not** silently initiate a scan.

---

## 4. Market selection and multilingual research

Markets must be user-selected independently of industries and categories. Initial country examples:

- **North America:** United States, Canada, Mexico.
- **Europe:** United Kingdom, Germany, France, Italy, Spain, Netherlands, and other user-added countries.
- **Asia:** Vietnam, Japan, South Korea, China, Thailand, Singapore, Malaysia, Indonesia, Philippines, India, and other user-added countries.

Support one country, multiple countries, whole regions, custom locations, and **cities only where trustworthy localized data exists** (e.g. New York, Los Angeles, Tokyo, Seoul, Hanoi, Ho Chi Minh City).

Use relevant languages and query aliases (English, Vietnamese, Japanese, Korean, Chinese, German, French, etc.) while preserving source-language names and canonical product names. Do not infer that a product is popular in Japan solely because it appeared on a Japanese website. Store geographic attribution and confidence supported by evidence.

---

## 5. Source ingestion, verification, and compliant access

Build **pluggable source adapters** and a configurable source-to-industry/market registry.

### 5.1 Social/community sources

Research permitted public/authorized information from TikTok, Instagram, YouTube, Reddit, Pinterest, X/Twitter, and permitted public Facebook content. Capture when available:

- Exact source post URL, platform, author/source ID, publication timestamp, collection timestamp.
- Product references, keywords, hashtags, engagement (views, likes, comments, shares), discussion frequency.
- Market/language relevance and independently attributable evidence.

### 5.2 Editorial, official and specialist sources

Fashion examples: Sneaker News, Hypebeast, Highsnobiety, Complex, Nice Kicks, Sole Retriever, House of Heat, KicksOnFire, Footwear News. For other industries use appropriate technology, beauty, lifestyle, collectibles, and official announcement outlets. Include Google News, RSS, public structured metadata, and localized sources when permitted.

**Extract the exact individual product mentioned**, not merely article headlines.

### 5.3 Retail and marketplace sources

Examples: Nike, Adidas, New Balance, ASICS, Foot Locker, JD Sports, END., SNS, KicksCrew, StockX, GOAT, Zalando, ABC-MART, Musinsa, and suitable industry-specific retailers. Capture verified product-detail links, SKU/model, images, price/currency, market, release date, stock state, and genuine retail signals **when accessible**. A new listing or unavailable stock is not automatically proof of strong sales.

### 5.4 Search-interest sources

Integrate Google Trends and other permitted search-trend sources as available. Differentiate **relative index values** from absolute volumes and do not invent unavailable metrics or use incomparable geographic data without normalization.

### 5.5 Source compliance and honest status

- Prefer official APIs, RSS feeds, published structured data, search indexes, and compliant public fetching.
- Respect access controls, rate limits, applicable site rules, and terms. Do not bypass CAPTCHAs, logins, paywalls, or anti-bot systems.
- Mark sources `WORKING`, `RATE_LIMITED`, `AUTH_REQUIRED`, `BLOCKED`, `ERROR`, or `NOT_CONFIGURED`; do not claim success after an inaccessible request.
- Support adapter-level retries, cooldown, structured errors, and independent failure recovery.
- Store source origin, publication time, observed time, and provenance. Deduplicate syndication/reposts before counting independent mentions.

---

## 6. Collection and canonicalization pipeline

Implement this workflow:

1. Load user-selected scan preset (markets × industries × categories × sources).
2. Generate local-language discovery keywords and aliases.
3. Collect permitted posts, feeds, articles, listings, and product pages.
4. Extract product-level entities and claims.
5. Normalize brand/model/colorway/version/SKU and assign canonical product IDs.
6. Associate evidence with its original URL and geographic context.
7. Discover primary product page, alternative product pages, and image URL.
8. Validate product identity and URLs; preserve confidence and unresolved fields.
9. Deduplicate products and evidence while preserving multi-market/multi-category associations.
10. Compute market-specific trend metrics and evidence coverage.
11. Compute Early Trend and Opportunity metrics where history is sufficient.
12. Update release/rumor state; detect new or changed events.
13. Persist raw evidence, aggregate observations, calculations, and job history.
14. Refresh the relevant table rows, charts, and export datasets.

Canonical identity must account for important variants: **sneaker release year/colorway/SKU; electronics model/version/capacity; collectibles edition/series; beauty variant/size**. Similar text alone does not prove identity.

---

## 7. MODULE 1 — Trend Dashboard

Display total discoveries, HOT NOW, RISING FAST, upcoming hype, trending brands/categories/markets, discovery dates, last scan status, data-source health, and changes since last scan. Provide charts of brand/category distribution, trend changes, and market breakdown with filters for country, industry, category, source, status, confidence, and time window (24h, 3d, 7d, 14d, 30d, 90d, custom).

### Trend Score (0–100, configurable per industry)

Suggested default weights:

| Signal | Weight |
|---|---:|
| Social momentum | 25% |
| Search interest | 20% |
| Independent editorial coverage | 15% |
| Retail / marketplace signals | 20% |
| Growth velocity | 15% |
| Independent source diversity | 5% |

Statuses: `HOT NOW`, `RISING FAST`, `UPCOMING HYPE`, `STABLE DEMAND`, `DECLINING`, `INSUFFICIENT DATA`.

Expose the score breakdown, confidence, data coverage, and explanation backed by observations. Do not treat missing data as confirmed zero interest. Avoid comparing raw unnormalized scores across industries or countries.

---

## 8. MODULE 2 — Product Research Sheet (highest UI priority)

Create a **Google Sheets-like, dense, fast, editable-selection research grid** using AG Grid Community or TanStack Table. Support virtualized/paginated large datasets, selectable cells and rows, search, sorting, filtering, resizing, column reordering, column visibility, thumbnails, opening links, and expandable evidence detail panels.

### Default columns (each in its own cell)

| Order | Column |
|---:|---|
| 1 | Industry |
| 2 | Category |
| 3 | Subcategory |
| 4 | Market / Region |
| 5 | Country |
| 6 | Brand |
| 7 | Product Name |
| 8 | Model / Colorway / Version |
| 9 | SKU / Model Number |
| 10 | Product Image URL |
| 11 | **Best Product Information URL (Primary Display URL)** |
| 12 | Best Link Type (Official / Article / Review / Release / Retailer / Other) |
| 13 | Alternative Information URL 1 |
| 14 | Alternative Information URL 2 |
| 15 | **Optional Purchase URL** |
| 16 | Reference URL 1 |
| 17 | Reference URL 2 |
| 18 | Reference URL 3 |
| 19 | Source Platforms |
| 20 | Trend Score |
| 21 | Trend Status |
| 22 | Early Signal Score |
| 23 | Opportunity Score (where applicable) |
| 24 | Evidence Confidence |
| 25 | Data Coverage |
| 26 | Trend Explanation |
| 27 | Release Status |
| 28 | First Detected |
| 29 | Last Seen / Updated |
| 30 | Product Link Verification Status |
| 31 | Actions / Find Product Links |

The **Best Product Information URL** is the most relevant, detailed, verifiable page focused on the exact product. It MAY be a news article, review, brand presentation, release article, or retail product page. **A shopping link is NOT required.** Keep **all** evidence in normalized records; three visible references are a convenient preview, not a storage limitation. Provide industry-specific column presets. Default export is one product per market; optionally expand one row per product-category association.

### Google Sheets copy/paste

Provide:

- `COPY TO GOOGLE SHEETS` — selectable scope: selected rows / filtered rows / all rows; optional headers.
- `COPY SELECTED CELLS`, `COPY SELECTED ROWS`, `COPY ALL FILTERED`.
- `EXPORT CSV`, `EXPORT XLSX`.
- Copy raw image URLs, or generate Google Sheets `=IMAGE("https://example.com/photo.jpg")` only for valid image URLs.
- Export visible column order and configurable hidden-column behavior.
- Produce correctly quoted/escaped **TSV** so tabs, quotes, line breaks, null cells, and column boundaries paste into Google Sheets reliably.
- URLs must be present as **plain, individually copyable strings**, not only icon controls.
- Verify a multi-row/multi-column Google Sheets paste using automated fixtures and tests.

---

## 9. MODULE 3 — Upcoming Releases & Rumors

Track future launches for **all selected industries**, including unconfirmed and rumored products.

Statuses:

- `OFFICIALLY CONFIRMED`
- `RETAILER LISTED`
- `REPORTED / EXPECTED`
- `RUMORED`
- `LEAKED`
- `DELAYED`
- `CANCELLED`
- `RELEASED`

Do not label rumors as official; do not treat leaked renders as verified final designs. Preserve original source URLs, source credibility, release-date revisions, and market-specific date differences. Support uncertain dates such as `Spring 2027`, `Q1 2027`, `2027`, and `TBA` without inventing an exact day.

### Upcoming table columns

Market, Country, Industry, Category, Brand, Product Name, Model/Variant, SKU, Image URL, Best Product Information URL, Optional Official/Purchase URL, Expected Release Date, Date Precision, Release Status, Rumor Confidence, Hype Score, Reference URL 1/2/3, Source Type, Expected Retail Price, Currency, First Reported, Last Updated, Latest Development.

Provide calendar and grid views, filters for confirmed vs rumor, date window (7/30/90 days, month, year, TBA), market, category, brand, and hype. Record every transition: rumor → confirmed, delay, cancel, release, source correction, and date change.

**Rumor Confidence (`HIGH`, `MEDIUM`, `LOW`, `UNVERIFIED`) must be separate from Hype Score** and consider independent corroboration, official/retailer evidence, contradictions, and source reliability. Preserve disproven rumor history rather than deleting it.

---

## 10. MODULE 4 — Trend Opportunity Finder

Identify products rising in one or more **Source Markets** but not yet comparably popular, available, or covered in a chosen **Target Market**. Allow all combinations of selected markets; initial editable preset: **Japan + South Korea + Vietnam → United States**.

Opportunity types:

- `EARLY MARKET OPPORTUNITY`
- `CROSS-MARKET BREAKOUT`
- `EMERGING TREND`
- `MARKET GAP`
- `UPCOMING OPPORTUNITY`
- `SATURATED TREND`

### Opportunity Score (0–100, adjustable)

| Dimension | Weight |
|---|---:|
| Source market momentum | 20% |
| Target market early growth | 20% |
| Evidence-based market gap | 20% |
| Search acceleration | 15% |
| Retail availability gap | 10% |
| Multi-market validation | 10% |
| Trend freshness | 5% |

Normalize market signals and control for source coverage. **Missing target-market information is not evidence of low popularity.** Distinguish verified low demand, limited observations, and insufficient data. Never present scores as certain sales forecasts.

### Opportunity table columns

Product Name, Brand, Industry, Category, SKU, Image URL, Source Markets, Target Market, Source Trend Score, Target Trend Score, Source Growth 7D, Target Growth 7D, Opportunity Score, Opportunity Type, Evidence Confidence, Data Coverage, Risk Level, Best Product Information URL, Optional Purchase URL, Source Evidence URL 1/2, Target Evidence URL, Release Status, Availability, Explanation, First Detected, Last Updated.

Offer side-by-side country comparisons and trend-history charts only when sufficient real observations exist.

### Opportunity Shortlist

Persist product, target market, priority, notes, research status, supplier check, marketing test status, review timestamp. Suggested statuses: `Researching`, `Supplier Check`, `Ready to Test`, `Running Ads`, `Monitoring`, `Rejected`. Do not delete saved entries when rankings change.

---

## 11. MODULE 5 — Early Trend Radar

Create a dedicated engine that detects **emerging products before they achieve high absolute popularity**.

Signals:

1. **Mention Velocity** — observed mentions over 24h, 3d, 7d, 14d, 30d; compare equal periods.
2. **Mention Acceleration** — growth rate itself speeding up over time.
3. **Independent Source Diversity** — distinct creators/outlets, removing reposts and syndication.
4. **Search Interest Growth** — comparable periods and market-specific indices.
5. **Engagement Momentum** — available likes/views/comments/shares with source context.
6. **Retail Signals** — verified new listings, restocks, retailer expansion, or comparable indicators.

### Early Signal Score (0–100, adjustable)

| Dimension | Weight |
|---|---:|
| Mention velocity | 20% |
| Mention acceleration | 25% |
| Search interest growth | 20% |
| Independent source diversity | 15% |
| Engagement momentum | 10% |
| Retail signals | 10% |

Lifecycle stages: `NEW SIGNAL`, `EARLY RISING`, `ACCELERATING`, `BREAKOUT`, `MAINSTREAM`, `SATURATED`, `COOLING DOWN`, `INSUFFICIENT DATA`.

Use rolling averages, baseline comparisons, smoothing, outlier checks, sample-size safeguards, independent source minimums, and coverage indicators. A jump from two to six mentions does not automatically equal a high-confidence breakout. Without history, show `NEW SIGNAL — INSUFFICIENT HISTORY` and keep provisional metrics separate from verified growth.

### Early Trend table columns

Market, Country, Industry, Category, Brand, Product Name, Model/Variant, SKU, Image URL, Best Product Information URL, Optional Purchase URL, Early Signal Score, Lifecycle Stage, Mention Growth 3D, Mention Growth 7D, Mention Growth 14D, Mention Acceleration, Search Growth, Independent Sources, Evidence Confidence, Data Coverage, First Detected, Latest Signal, Reference URL 1/2/3, Explanation, Last Updated.

Integrate Early Trend with market comparisons, Upcoming Releases/Rumors, history, watchlist, automatic scans, manual refresh, and Sheets export.

---

## 12. Product Link Finder — best information links and optional purchase links

Every product in **all five modules** must expose **`Find Product Links`**, with the clearer action label **`Find Product Information Links`** allowed. Clicking it must **only search for that selected product**, not trigger a global/category-wide scan.

### Primary goal — the most informative page, NOT necessarily a shopping page

For each product, locate and select a **Best Product Information URL (Primary Display URL)** that presents the **exact product** and offers the most useful verified information. Valid candidates include:

1. Detailed official brand/model introduction pages.
2. Substantive product-specific news articles, release announcements, or editorial reviews.
3. Product-specific technical specification or release calendar pages.
4. Detailed retailer product listings or marketplace item pages.
5. Other trustworthy public pages with clear, substantial product-level information.

**Never prioritize a buy button over richer, more relevant information.** An article may outrank a storefront if it provides more accurate identity, pictures, description, model details, release context, specifications, and verifiable source information. The primary URL can therefore be a news article or review. **No purchase link is required** to consider the product research record successfully resolved.

### Candidate evaluation and selection

1. Load canonical product identity (brand, name, model, variant, SKU/version/edition).
2. Search compliant public sources, articles, official brand sites, retailers, and product-search indexes relevant to the selected industry/market.
3. Verify each page focuses on the **same exact product**, using SKU/model, edition, release year, colorway, specifications and other relevant identifiers.
4. Classify identity match: `EXACT MATCH`, `HIGH CONFIDENCE`, `POSSIBLE MATCH`, `REJECTED`.
5. Score verified candidates for **product-specific information completeness**, e.g. accurate full name, product images, detailed description/specifications, SKU, variant, release information, credibility, and page accessibility. Scores must be explainable and based on observed page contents; do not fabricate fields.
6. Assign the highest-quality sufficiently verified candidate as **Best Product Information URL**, regardless of whether it sells anything. If candidates are close, prefer the stronger original/authoritative source and more current, product-specific content.
7. Store multiple candidate pages and their page type: `OFFICIAL_INFO`, `ARTICLE`, `REVIEW`, `RELEASE_INFO`, `RETAIL_PRODUCT`, `MARKETPLACE_PRODUCT`, `OTHER`.
8. Store **Optional Purchase URL** separately when an actual verified purchasable product page exists; do not conflate articles/previews with purchase URLs.
9. Queue possible identity matches for manual review. Never assign unrelated product pages.
10. Update **only the selected product** and expose checked sources, candidate matches, selected primary URL, missing fields, verification time, and failures.
11. Let the user manually change the primary information URL from the verified candidates.

**Examples:** A comprehensive sneaker article about an exact colorway may be the main link; an official shoe listing is kept as an optional purchase link. For a rumored launch, a credible rumor article can be the main link even when no sales listing exists. For electronics, a detailed official specifications page can be preferred over a short shopping listing.

### Data schema and export

Maintain a normalized `product_links` table with product ID, URL, page type, source, country, identity match confidence, verified information fields, information completeness score, is_primary_information_url, is_purchase_url, first_found_at, last_verified_at, and provenance. Only attach observed prices, currency, or stock to applicable retailer links when verified.

Display **Best Product Information URL** prominently in all product tables and product detail panels. Include independently copyable columns for **Best Product Information URL**, **Link Type**, **Alternative Information URL 1/2**, **Optional Purchase URL**, and **Reference URLs** in TSV/CSV/XLSX exports.

Bulk actions:

- `Find Links for Selected Products`.
- `Find Missing Information Links` (missing a verified primary information URL, not merely missing a shopping URL).
- Optional `Find Purchase Links` for users specifically seeking stores.
- Controlled queue, rate limits, checkpointing, pause/resume, deduplication, and partial-failure reporting.

A product with a verified informative article **must not be marked as missing a product link** solely because it lacks an e-commerce purchase link.

---

## 13. Smart Scan Manager — completely user-defined presets

The rows shown in the interface (e.g., `US Sneakers`, `Japan Streetwear`, `Electronics`, `Collectibles`, `Beauty & Personal Care`) are **examples only**. **THE USER CREATES AND CONTROLS EVERY PRESET.** Names are user-provided labels, not fixed taxonomy nodes.

Provide `Add New Scan Preset`, Edit, Rename, Duplicate, Delete, Enable/Disable. Each preset contains:

- Custom name.
- One or multiple markets, countries, optional cities.
- One or multiple industries/categories/subcategories.
- Include/exclude keywords, local-language aliases.
- Sources and source priorities.
- Priority schedule: Daily / Weekly / On Demand.
- Discovery or Tracking mode; Quick or Full scan.
- Enabled state.
- Last successful scan, last attempted scan, next scheduled scan.
- Optional resource limits and preferred export columns.

Example configuration (fully editable):

| Preset name | Markets | Categories | Priority |
|---|---|---|---|
| US Sneakers | United States | Air Jordan, Nike, Adidas | P1 Daily |
| Asia Electronics | Japan, South Korea, Vietnam | Earbuds, Gadgets | P2 Weekly |
| Global Collectibles | US, Japan, Europe | LEGO, Figures | P2 Weekly |
| Beauty Research | US, South Korea | Skincare, Makeup | P3 On Demand |

Deleting a preset **must not delete products, evidence, scan history, or saved lists**.

---

## 14. Three scan priorities and default schedules

Timezone for schedules: **`Asia/Ho_Chi_Minh`** (Vietnam, UTC+7).

| Priority | Default cadence | Purpose |
|---|---|---|
| **P1 — Daily** | **07:00 every day**, including weekends | Primary business categories; incremental trend/release/early-signal updates |
| **P2 — Weekly** | **07:00 every Monday** | Deeper discovery and verification for secondary research categories |
| **P3 — On Demand** | **No automatic schedule** | Only scan when the user explicitly invokes Refresh |

Daily and weekly presets must be configurable independently. A one-off manual scan **must not silently overwrite** the saved daily/weekly preset. No automatic scan may start for P3 unless the user changes its priority.

### Manual controls

- `Refresh Now` on dashboard and relevant pages.
- `Quick Refresh` — recent data, incremental fetch, efficient updates.
- `Full Refresh` — broader sources, deeper verification, preserve history.
- Run by individual product, selected rows, selected categories, industry, country, or named preset.
- Show source/job progress, discovered/updated products, failure counts, completion status, and elapsed time.

### Discovery vs Tracking

- **Discovery Scan:** search for *new* product identities and supporting references; usually resource-intensive.
- **Tracking Scan:** revisit known product identities and update observations, releases, early momentum, and opportunities; avoid unnecessarily rediscovering the full universe.

Both use the same persistent scan service but have independently configurable workloads.

---

## 15. Reliable scheduling and workload control

Implement a centralized, **persistent shared queue** for scheduled scans, manual scans, and bulk product-link jobs. Requirements:

- Deduplicate overlapping (market, category, source, time-window) work without losing preset-level completion reporting.
- Resource limits: global and per-source concurrency, per-source request rate, timeout, retries, max results, scan duration, batch size, cache TTL.
- Source-aware caching and optional ETag / Last-Modified; label cached records as cached rather than freshly observed.
- Incremental checkpoints, idempotent jobs, pause/resume/cancel, safe recovery after interruption, bounded exponential backoff, and cooldowns for failing sources.
- Job priority: user-triggered tasks may enter ahead of scheduled jobs, but scheduled jobs must not be starved indefinitely.
- Prevent duplicate schedule triggers across backend processes; ensure transactional database writes.
- On missed scheduled run, execute **one controlled catch-up scan** when the service restarts instead of enqueuing every missed run.
- Do not overwrite valid prior data with empty results after failures.

The scheduler must run **independently of the browser**. Provide Windows Task Scheduler or a reliable local service option, and document that **a powered-off computer cannot scan at 07:00**. For uninterrupted daily execution offer an optional always-on VPS/server deployment guide.

Provide **Scan Manager progress and history**: preset, priority, next run, last success, current source, queued/running/completed/failed tasks, new/updated products, errors, checkpoints, and failure details.

Optional adaptive optimization may prioritize emerging trends and imminent releases **within user-authorized scan schedules**. Never silently change an On Demand preset into an automatic one.

---

## 16. What's New Since Last Scan

Unified change feed with source URLs and timestamps:

- New products; new evidence; new primary/alternative product links.
- Newly HOT / RISING FAST; new Early Signals, ACCELERATING, BREAKOUT.
- New rumors, confirmations, delays, cancellations, or revised launch dates.
- New cross-market opportunities and meaningful score changes.
- Product momentum cooling down.

Support `Show only new or changed`, market/industry/category/time filters, and links to the affected product. Compare against actual previous successful observations; do not call a routine recomputation a market change.

---

## 17. Data architecture and persistence

Initial backend: SQLite, with a documented migration path to PostgreSQL. Use migrations (e.g., Alembic). Suggested tables/entities:

- `industries`, `categories`, `category_hierarchy`, `product_categories`
- `products`, `product_aliases`, `product_attribute_definitions`, `product_attribute_values`
- `product_links`, `evidence`, `source_registry`, `source_status`, `source_industry_mapping`
- `scan_presets`, `scan_jobs`, `scan_tasks`, `scan_checkpoints`, `scan_history`
- `product_market_trends`, `trend_history`, `market_signal_coverage`
- `upcoming_releases`, `release_history`
- `product_signal_observations`, `product_daily_signal_metrics`, `product_early_signal_scores`, `product_lifecycle_history`, `early_signal_events`
- `opportunity_scores`, `opportunity_history`, `shortlists`

Design indexes and uniqueness rules around canonical product IDs, evidence identity, source/market timestamps, and normalized product links. Preserve raw observations independently from derived scores so algorithms can be revised. Recompute scores from stored observations if weights change. Support market- and source-specific provenance. Never reset an existing working database as part of an upgrade without explicit authorization.

---

## 18. Settings and security

Settings UI must include:

- Market/language defaults; industry/category editor; scan presets.
- Sources, source health, credentials, custom permitted URLs and keywords.
- Default timezone, scan frequency, priority, job resource limits.
- Industry-specific Trend, Early Signal, and Opportunity scoring weights.
- Confidence thresholds, evidence coverage rules, shortlist filters.
- Google Sheets output: column presets/order, headings, images, CSV/XLSX/TSV.
- Theme and display language.

Store secrets only in environment variables or appropriate secure configuration; ship `.env.example` without secrets. Do not depend on a paid AI provider for basic data processing, dashboard, and export functionality. Optional AI-assisted entity extraction/classification must be configurable and must not invent missing source facts.

---

## 19. Suggested technology stack

- **Backend:** Python 3.12+, FastAPI, httpx, BeautifulSoup, Playwright **only where permitted**, Pydantic, SQLAlchemy, Alembic, APScheduler or equivalent persistent scheduler.
- **Frontend:** React + TypeScript + Vite + Tailwind CSS; AG Grid Community or TanStack Table.
- **Storage:** SQLite initially, PostgreSQL-ready design.
- **Processing/export:** pandas, openpyxl, RapidFuzz, python-dateutil.
- **Testing:** pytest for backend; suitable frontend test runner and browser end-to-end tests for grid clipboard/export flows.

Choose equivalent tools when demonstrably appropriate; document deviations. Optimize for Windows local use without preventing later server deployment.

---

## 20. Windows deployment and deliverables

Deliver a functional repository with:

- Backend and frontend source code, database schema/migrations, source adapters, processors, scoring engines, and tables.
- Manual refresh and persistent scheduler, scan queue, link finder, five research modules, and management pages.
- `README.md`, `.env.example`, dependency lockfiles, installation instructions, Windows `.bat` / PowerShell startup script, scheduled-task setup and verification instructions.
- Sample configuration, **clearly labeled demo/test fixtures**, and a documented way to fetch real live permitted data.
- Source support matrix listing working sources, restricted sources, required credentials, known limitations, and tested features.
- Automated tests with runnable commands and results.
- Optional guide for deployment on an always-on VPS/cloud server.

Make ordinary use possible without requiring the user to edit code whenever they add a country, category, industry, or preset.

---

## 21. Test plan and quality gates

At minimum test:

**Product and sources:** entity extraction, canonical identity, aliases across languages, SKU and variant resolution, wrong-link rejection, information-page relevance/completeness, article-vs-storefront ranking, optional purchase URLs, image URL handling, source duplication, country attribution, source failure states.

**Taxonomy/presets:** custom industry, nested/multiple category selection, cross-category product dedup, rename/delete preset, multi-country multi-industry preset, saved preferences, category filters vs scan scope.

**Trend/rumor/opportunity:** trend scoring, early velocity and acceleration, small-sample safeguards, independent source diversity, missing history, coverage differences, cross-market comparability, rumor confidence and release-date uncertainty, rumor-to-confirmed transitions, opportunity classifications and shortlists.

**Links:** Find Product Links single product, bulk selected, find missing information pages, exact-product matching, prefer richer article over thin retailer listing when justified, distinct primary information URL vs optional purchase URL, article/rumor-only success state, pause/resume, persistence, link export.

**Scheduler/queue:** daily 07:00 timezone, Monday 07:00, P3 manual-only, manual Quick/Full override, simultaneous overlapping jobs, rate limits, source failure, checkpoints, missed run catch-up, restart recovery, database transactions, no phantom successes.

**Exports/UI:** cell/multi-row selection, filters and sorting, copy exactly selected/filtered scope, TSV escaping/column alignment, raw link strings, valid IMAGE formulas, CSV and XLSX, large-grid performance, preserved rows after restart.

Synthetic fixtures may be used in tests, but must never be described as live market findings.

---

## 22. Phased execution plan for Codex

**Phase 1 — Working MVP**

- Inspect existing repository and protect working code/data.
- Database, industry/category/market selector, user-defined scan presets.
- Source registry and at least one **working permitted live source adapter**.
- Product extraction, normalization, direct URLs, evidence records.
- Product Research Sheet, TSV copy, CSV/XLSX export.
- Manual Quick Refresh with persistence and basic tests.

**Phase 2 — Scan reliability and launches**

- Shared queue, incremental Discovery/Tracking, caching/checkpoints.
- P1 Daily and P2 Weekly scheduler, P3 On Demand, Windows setup.
- Trend Dashboard, Upcoming Releases & Rumors, history and confidence.

**Phase 3 — Link finder and early detection**

- Single/bulk Product Link Finder with verification.
- Early Trend Radar, velocity, acceleration, source diversity, watchlist.
- Unified What's New Since Last Scan.

**Phase 4 — Cross-market intelligence**

- Trend Opportunity Finder, normalized market comparison, opportunity scores, shortlist, release integration.

**Phase 5 — Hardening**

- End-to-end tests, performance on large tables, recovery tests, documentation, source support matrix, Windows deployment verification.

Do not stop at writing a design plan. Implement the working MVP first, run tests, fix failures, then continue through achievable phases. Clearly report genuine blockers (credentials/source limitations) and deliver the remaining working features rather than faking coverage.

---

## 23. Final acceptance checklist

- [ ] One application with **five integrated research modules**.
- [ ] Fully configurable **industries/categories/subcategories**; multiple selections.
- [ ] Fully configurable **countries/regions**; multilingual aliases.
- [ ] User-defined **Smart Scan presets**, not hardcoded example rows.
- [ ] **P1 daily 07:00**, **P2 Monday 07:00**, **P3 manual-only**, Asia/Ho_Chi_Minh.
- [ ] **Manual Quick / Full Refresh** scoped to products, categories, markets, or presets.
- [ ] Separate **Discovery Scan** and **Tracking Scan**, reliable queue and checkpoints.
- [ ] At least one real permitted data source produces real product/evidence records.
- [ ] Product name, brand, SKU/model, image URL, **best product information URL (including articles/reviews)**, reference URLs and optional purchase URL stored separately.
- [ ] **Find Product Links** for each product, plus selected/missing bulk lookup; no whole-system rescan for one link.
- [ ] Multiple verified product information pages, match confidence, information-completeness ranking, and user-selectable primary page; retailer purchase links optional.
- [ ] Upcoming launches and **rumors** clearly labeled, with date uncertainty and historical changes.
- [ ] Early Trend scores and lifecycle classes use real observed history and sample-size safeguards.
- [ ] Opportunity Finder compares selected markets without treating missing data as zero interest.
- [ ] Product Research Sheet supports dense grid interaction and **copy/paste into Google Sheets**.
- [ ] TSV, CSV, XLSX, and raw image links / IMAGE formulas verified.
- [ ] Historical records, saved lists, and presets survive refresh/restart/upgrades.
- [ ] Failed/restricted sources are reported honestly.
- [ ] Windows startup, scheduler setup, README, .env.example and automated tests supplied.

### Final instruction to Codex

**Build a reliable, real-data, multi-industry product intelligence system. The user chooses the industries, categories, countries, presets, and scan priorities. Every meaningful product finding should expose its name, **best informative product-specific page URL (including an article if strongest)**, independent reference URLs, optional shopping URL, market context, and copyable Google Sheets fields. Never replace missing evidence with invented data.**
