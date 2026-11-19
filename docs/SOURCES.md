# Source support matrix

Status values shown in the app: `WORKING`, `RATE_LIMITED`, `AUTH_REQUIRED`, `BLOCKED`, `ERROR`, `NOT_CONFIGURED`, `UNTESTED`.
A source is only marked `WORKING` after a real successful request on **your** machine.

| Source | Adapter | Type | Markets | Credentials | Verified in build environment | Notes |
|---|---|---|---|---|---|---|
| Google News RSS search | google_news | Editorial aggregator | every market with an `hl|gl|ceid` edition (US, CA, MX, GB, DE, FR, IT, ES, NL, VN, JP, KR, TH, SG, MY, ID, PH, IN) | none | ❌ network blocked in sandbox | Item links are `news.google.com` redirect URLs → flagged *aggregator*; the publisher name is kept as the independent outlet. China has no edition. |
| Sneaker News | rss | Editorial | US | none | ❌ | publisher feed `https://sneakernews.com/feed/` |
| Nice Kicks | rss | Editorial | US | none | ❌ | |
| Hypebeast | rss | Editorial | GLOBAL (not attributed to a country) | none | ❌ | |
| The Verge / Engadget | rss | Editorial | US | none | ❌ | |
| 9to5Mac / GSMArena | rss | Editorial | GLOBAL | none | ❌ | frequent rumor coverage → claims are labelled RUMORED/LEAKED |
| The Brothers Brick | rss | Editorial (LEGO) | GLOBAL | none | ❌ | |
| Allure | rss | Editorial (beauty) | US | none | ❌ | |
| Reddit r/Sneakers RSS | rss | Social | GLOBAL | none | ❌ | **disabled by default** – anonymous clients are often rate-limited |
| YouTube Data API v3 | youtube | Social (views/likes/comments) | per market (`regionCode`) | `YOUTUBE_API_KEY` (free quota) | ❌ | `NOT_CONFIGURED` until the key is set |
| TikTok | unsupported | Social | – | TikTok Research API approval | – | no scraping |
| Instagram | unsupported | Social | – | Meta Graph API + app review | – | no scraping |
| X / Twitter | unsupported | Social | – | paid X API | – | no scraping |
| Google Trends | unsupported | Search interest | – | no official public API | – | search-interest signal stays *not observed* |
| Hypebeast JP / KR, ITmedia, Gizmodo JP, VnExpress Số hóa | rss | Editorial | JP / KR / VN | none | ❌ URL not verified | added in v0.2 - press Test |
| Reddit r/gadgets RSS | rss | Social | GLOBAL | none | ❌ | v0.2, enabled; r/Sneakers now enabled too |
| Manual capture (bookmarklet / bulk paste) | manual | Social / Editorial / Retail by domain | the market you choose | none | ✅ tested | pages YOU browsed; engagement only as shown on the page |
| Google Trends CSV import | trends_import | Search interest | per CSV geo | none | ✅ tested | relative index; only latest import per product/market is used |
| DEMO fixture | fixture | synthetic | US/JP/KR/VN/GB | – | ✅ | tests + UI preview only; every record has `is_fixture=true` |

You can add any permitted RSS feed in **Source Manager → Add a permitted RSS feed** (choose the market it really represents;
use `GLOBAL` if the outlet is international). Do not add feeds whose terms forbid automated access.

## Sneaker research channels (added in v0.9)
| Channel | How it is read | Notes |
|---|---|---|
| Sneaker News, Nice Kicks, Hypebeast, KicksOnFire | RSS (WordPress pages 2-5) | already included before v0.9 |
| Sneaker Bar Detroit | RSS `sneakerbardetroit.com/feed/` | |
| JustFreshKicks | RSS `justfreshkicks.com/feed/` | URL not verified from the build environment |
| House of Heat | RSS `houseofheat.co/feed` | URL not verified - if Test fails use the bookmarklet |
| Complex Sneakers | RSS `complex.com/sneakers/rss` | no documented public feed - may fail; bookmarklet fallback |
| Hypebeast Footwear | RSS `hypebeast.com/footwear/feed` | footwear-only section |
| SBD Air Jordan / sneaker release dates | `release_calendar` page parser | entries filed as REPORTED / EXPECTED (US dates & prices) |
| X (Twitter) accounts, Sniperkicks | not crawled | X has no free API and needs login; use the bookmarklet on posts you read. Most of these accounts post links to the same articles their websites publish, which the feeds above already cover. |

## Compliance behaviour
* `robots.txt` is honoured for every page fetch; a disallowed URL is reported as `BLOCKED`.
* HTTP 401/407 → `AUTH_REQUIRED`, 403 or CAPTCHA page → `BLOCKED`, 429 → `RATE_LIMITED`; nothing is bypassed.
* Per-source rate limit (requests/minute, editable), retries with bounded backoff for transient errors, cooldown after repeated failures.
* ETag / Last-Modified conditional requests + cache TTL; cached results are labelled `cached` in the job detail.
* A failed fetch never deletes or overwrites earlier evidence.

## Known limitations
* Product extraction is rule-based on headlines: it needs a brand in the brand dictionary plus a model token. Add brands/aliases in
  *Industries & Categories → Brand dictionary*. Possible duplicates are flagged `review`, never auto-merged.
* Country attribution comes from the source edition (e.g. Google News JP). A Japanese-language page alone does not make a product "popular in Japan".
* Social, search-interest and retail signals are empty until a permitted source for them is configured; scores show the reduced coverage.
