"""Initial *example* data. Everything here is editable in the UI and only inserted when missing,
so re-running never overwrites user changes."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Brand, Category, Industry, Market, ProductAttributeDefinition, ScanPreset, Setting, Source

INDUSTRIES: dict[str, dict] = {
    "Fashion & Footwear": {
        "attrs": [("colorway", "Colorway", True), ("size_range", "Sizes", False), ("release_year", "Release year", True)],
        "cats": {
            "Sneakers": {"kw": ["sneaker", "sneakers", "release date", "colorway", "retro"],
                         "local": {"ja": ["スニーカー"], "ko": ["스니커즈"], "vi": ["giày sneaker"], "zh": ["运动鞋"], "de": ["Sneaker"], "fr": ["baskets"]},
                         "subs": {"Air Jordan": ["Jordan"], "Nike": ["Nike"], "Adidas": ["adidas"], "ASICS": ["ASICS"], "New Balance": ["New Balance"]}},
            "Clothing": {"kw": ["hoodie", "jacket", "jersey", "denim", "t-shirt"], "local": {"vi": ["áo hoodie", "áo khoác"], "ja": ["パーカー"]},
                         "subs": {"Hoodies": [], "Jackets": [], "Jerseys": [], "Denim": []}},
            "Bags & Accessories": {"kw": ["bag", "backpack", "cap", "accessory"], "local": {}, "subs": {}},
            "Sneakerboots": {"kw": ["sneakerboot", "boot"], "local": {}, "subs": {}},
        },
    },
    "Electronics & Technology": {
        "attrs": [("model", "Model", True), ("storage", "Storage", True), ("connectivity", "Connectivity", False)],
        "cats": {
            "Smartphones": {"kw": ["smartphone", "phone", "iphone*", "galaxy s*", "galaxy z*", "pixel 1*", "pixel 9*", "nothing phone*", "oneplus 1*", "xiaomi 1*"], "local": {"ja": ["スマートフォン"], "ko": ["스마트폰"], "vi": ["điện thoại"]}, "subs": {}},
            "Headphones & Earbuds": {"kw": ["earbuds", "headphones", "airpods*", "galaxy buds*", "wh-1000*", "wf-1000*", "quietcomfort*", "soundcore*", "nothing ear*"], "local": {"ja": ["イヤホン"], "ko": ["이어폰"], "vi": ["tai nghe"]}, "subs": {}},
            "Gaming Devices": {"kw": ["console", "handheld", "gaming", "switch 2", "playstation*", "xbox*", "steam deck"], "local": {}, "subs": {}},
            "PC Accessories": {"kw": ["keyboard", "mouse", "monitor"], "local": {}, "subs": {}},
            "AI Gadgets": {"kw": ["AI device", "AI wearable", "AI pin"], "local": {}, "subs": {}},
            "Smart Home": {"kw": ["smart home", "smart speaker"], "local": {}, "subs": {}},
        },
    },
    "Beauty & Personal Care": {
        "attrs": [("variant", "Variant/Shade", True), ("size", "Size", True)],
        "cats": {"Skincare": {"kw": ["serum", "sunscreen", "moisturizer", "skincare", "toner", "essence"], "brands": ["COSRX", "Laneige"], "local": {"ko": ["스킨케어"], "vi": ["dưỡng da"]}, "subs": {}},
                 "Makeup": {"kw": ["lipstick", "foundation", "makeup"], "local": {}, "subs": {}},
                 "Fragrance": {"kw": ["fragrance", "perfume", "eau de parfum"], "local": {}, "subs": {}},
                 "Haircare": {"kw": ["shampoo", "hair dryer", "haircare"], "local": {}, "subs": {}}},
    },
    "Home & Living": {"attrs": [], "cats": {"Furniture": {"kw": ["chair", "sofa"], "local": {}, "subs": {}},
                                            "Kitchen": {"kw": ["kitchen", "air fryer", "coffee maker"], "local": {}, "subs": {}}}},
    "Sports & Outdoor": {"attrs": [], "cats": {"Running": {"kw": ["running shoe", "marathon"], "local": {}, "subs": {}},
                                               "Camping": {"kw": ["tent", "camping"], "local": {}, "subs": {}}}},
    "Toys & Collectibles": {
        "attrs": [("edition", "Edition", True), ("series", "Series", True)],
        "cats": {"LEGO": {"kw": ["LEGO set"], "brands": ["LEGO"], "local": {}, "subs": {}},
                 "Figures": {"kw": ["figure", "figures", "vinyl figure", "labubu"], "brands": ["Pop Mart", "Bandai"], "local": {"ja": ["フィギュア"]}, "subs": {}},
                 "Trading Cards": {"kw": ["trading card", "booster"], "local": {}, "subs": {}}},
    },
    "Automotive Accessories": {"attrs": [], "cats": {"Car Accessories": {"kw": ["dash cam", "car accessory"], "local": {}, "subs": {}}}},
    "Lifestyle & Pet": {"attrs": [], "cats": {"Pet": {"kw": ["pet", "dog", "cat"], "local": {}, "subs": {}},
                                              "Travel": {"kw": ["luggage", "travel"], "local": {}, "subs": {}}}},
    "Food & Beverage": {"attrs": [], "cats": {"Snacks": {"kw": ["snack"], "local": {}, "subs": {}},
                                              "Coffee": {"kw": ["coffee"], "local": {}, "subs": {}}}},
}

BRANDS = [
    ("Air Jordan", ["Jordan", "AJ"], ["nike.com", "jordan.com"], ["Fashion & Footwear"]),
    ("Nike", ["NIKE"], ["nike.com"], ["Fashion & Footwear", "Sports & Outdoor"]),
    ("adidas", ["Adidas", "adidas Originals"], ["adidas.com"], ["Fashion & Footwear", "Sports & Outdoor"]),
    ("New Balance", ["NB"], ["newbalance.com"], ["Fashion & Footwear"]),
    ("ASICS", ["Asics"], ["asics.com"], ["Fashion & Footwear", "Sports & Outdoor"]),
    ("PUMA", ["Puma"], ["puma.com"], ["Fashion & Footwear"]),
    ("Converse", [], ["converse.com"], ["Fashion & Footwear"]),
    ("Vans", [], ["vans.com"], ["Fashion & Footwear"]),
    ("Salomon", [], ["salomon.com"], ["Fashion & Footwear", "Sports & Outdoor"]),
    ("HOKA", ["Hoka"], ["hoka.com"], ["Fashion & Footwear", "Sports & Outdoor"]),
    ("On", ["On Running", "On Cloudmonster", "On Cloud"], ["on.com"], ["Sports & Outdoor"]),
    ("Supreme", [], ["supremenewyork.com"], ["Fashion & Footwear"]),
    ("Apple", [], ["apple.com"], ["Electronics & Technology"]),
    ("Samsung", ["Galaxy"], ["samsung.com"], ["Electronics & Technology"]),
    ("Google", ["Pixel"], ["store.google.com"], ["Electronics & Technology"]),
    ("Sony", [], ["sony.com"], ["Electronics & Technology"]),
    ("Xiaomi", [], ["mi.com"], ["Electronics & Technology"]),
    ("Nothing", ["Nothing Phone", "Nothing Ear", "CMF by Nothing"], ["nothing.tech"], ["Electronics & Technology"]),
    ("OnePlus", [], ["oneplus.com"], ["Electronics & Technology"]),
    ("Nintendo", [], ["nintendo.com"], ["Electronics & Technology"]),
    ("Bose", [], ["bose.com"], ["Electronics & Technology"]),
    ("Anker", ["Soundcore"], ["anker.com"], ["Electronics & Technology"]),
    ("Logitech", [], ["logitech.com"], ["Electronics & Technology"]),
    ("LEGO", [], ["lego.com"], ["Toys & Collectibles"]),
    ("Pop Mart", ["POP MART", "Labubu"], ["popmart.com"], ["Toys & Collectibles"]),
    ("Bandai", [], ["bandai.com"], ["Toys & Collectibles"]),
    ("Dyson", [], ["dyson.com"], ["Beauty & Personal Care", "Home & Living"]),
    ("COSRX", [], ["cosrx.com"], ["Beauty & Personal Care"]),
    ("Laneige", [], ["laneige.com"], ["Beauty & Personal Care"]),
]

# code, name, region, languages, google-news (hl, gl, ceid) or None, is_city, parent
MARKETS = [
    ("GLOBAL", "Global / Unattributed", "Global", ["en"], None, False, None),
    ("US", "United States", "North America", ["en"], ("en-US", "US", "US:en"), False, None),
    ("CA", "Canada", "North America", ["en", "fr"], ("en-CA", "CA", "CA:en"), False, None),
    ("MX", "Mexico", "North America", ["es"], ("es-419", "MX", "MX:es-419"), False, None),
    ("GB", "United Kingdom", "Europe", ["en"], ("en-GB", "GB", "GB:en"), False, None),
    ("DE", "Germany", "Europe", ["de"], ("de", "DE", "DE:de"), False, None),
    ("FR", "France", "Europe", ["fr"], ("fr", "FR", "FR:fr"), False, None),
    ("IT", "Italy", "Europe", ["it"], ("it", "IT", "IT:it"), False, None),
    ("ES", "Spain", "Europe", ["es"], ("es", "ES", "ES:es"), False, None),
    ("NL", "Netherlands", "Europe", ["nl"], ("nl", "NL", "NL:nl"), False, None),
    ("VN", "Vietnam", "Asia", ["vi"], ("vi", "VN", "VN:vi"), False, None),
    ("JP", "Japan", "Asia", ["ja"], ("ja", "JP", "JP:ja"), False, None),
    ("KR", "South Korea", "Asia", ["ko"], ("ko", "KR", "KR:ko"), False, None),
    ("CN", "China", "Asia", ["zh"], None, False, None),
    ("TH", "Thailand", "Asia", ["th"], ("th", "TH", "TH:th"), False, None),
    ("SG", "Singapore", "Asia", ["en"], ("en-SG", "SG", "SG:en"), False, None),
    ("MY", "Malaysia", "Asia", ["ms", "en"], ("en-MY", "MY", "MY:en"), False, None),
    ("ID", "Indonesia", "Asia", ["id"], ("id", "ID", "ID:id"), False, None),
    ("PH", "Philippines", "Asia", ["en"], ("en-PH", "PH", "PH:en"), False, None),
    ("IN", "India", "Asia", ["en", "hi"], ("en-IN", "IN", "IN:en"), False, None),
    ("US-NYC", "New York", "North America", ["en"], None, True, "US"),
    ("US-LA", "Los Angeles", "North America", ["en"], None, True, "US"),
    ("JP-TYO", "Tokyo", "Asia", ["ja"], None, True, "JP"),
    ("KR-SEL", "Seoul", "Asia", ["ko"], None, True, "KR"),
    ("VN-HAN", "Hanoi", "Asia", ["vi"], None, True, "VN"),
    ("VN-SGN", "Ho Chi Minh City", "Asia", ["vi"], None, True, "VN"),
]

# key, name, adapter, url, type, platform, industries, markets, credibility, enabled, notes
SOURCES = [
    ("google_news", "Google News RSS (per market)", "google_news", "https://news.google.com/rss/search", "EDITORIAL", "Google News",
     [], [], 0.6, True, "Public RSS search feed, localized by hl/gl/ceid. Item links are news.google.com redirect URLs (flagged as aggregator)."),
    ("sneakernews", "Sneaker News", "rss", "https://sneakernews.com/feed/", "EDITORIAL", "Sneaker News",
     ["Fashion & Footwear"], ["US"], 0.85, True, "Publisher RSS feed."),
    ("nicekicks", "Nice Kicks", "rss", "https://www.nicekicks.com/feed/", "EDITORIAL", "Nice Kicks",
     ["Fashion & Footwear"], ["US"], 0.8, True, "Publisher RSS feed."),
    ("hypebeast", "Hypebeast", "rss", "https://hypebeast.com/feed", "EDITORIAL", "Hypebeast",
     ["Fashion & Footwear", "Toys & Collectibles"], ["GLOBAL"], 0.8, True, "Publisher RSS feed; global audience, not attributed to a single country."),
    ("theverge", "The Verge", "rss", "https://www.theverge.com/rss/index.xml", "EDITORIAL", "The Verge",
     ["Electronics & Technology"], ["US"], 0.85, True, "Publisher RSS feed."),
    ("engadget", "Engadget", "rss", "https://www.engadget.com/rss.xml", "EDITORIAL", "Engadget",
     ["Electronics & Technology"], ["US"], 0.8, True, "Publisher RSS feed."),
    ("9to5mac", "9to5Mac", "rss", "https://9to5mac.com/feed/", "EDITORIAL", "9to5Mac",
     ["Electronics & Technology"], ["GLOBAL"], 0.8, True, "Publisher RSS feed; frequently reports rumors (claims are labeled)."),
    ("gsmarena", "GSMArena", "rss", "https://www.gsmarena.com/rss-news-reviews.php3", "EDITORIAL", "GSMArena",
     ["Electronics & Technology"], ["GLOBAL"], 0.8, True, "Publisher RSS feed."),
    ("brothersbrick", "The Brothers Brick", "rss", "https://www.brothers-brick.com/feed/", "EDITORIAL", "The Brothers Brick",
     ["Toys & Collectibles"], ["GLOBAL"], 0.7, True, "Publisher RSS feed (LEGO)."),
    ("allure", "Allure", "rss", "https://www.allure.com/feed/rss", "EDITORIAL", "Allure",
     ["Beauty & Personal Care"], ["US"], 0.75, True, "Publisher RSS feed."),
    ("reddit_sneakers", "Reddit r/Sneakers (RSS)", "rss", "https://www.reddit.com/r/Sneakers/.rss", "SOCIAL", "Reddit",
     ["Fashion & Footwear"], ["GLOBAL"], 0.5, False, "Public subreddit RSS. Disabled by default: Reddit rate-limits anonymous clients; enable if it works for you."),
    ("youtube", "YouTube Data API v3", "youtube", "https://www.googleapis.com/youtube/v3/search", "SOCIAL", "YouTube",
     [], [], 0.6, True, "Official API. Needs YOUTUBE_API_KEY in .env (free quota). Reports NOT_CONFIGURED without it."),
    ("tiktok", "TikTok Research API", "unsupported", None, "SOCIAL", "TikTok", [], [], 0.5, False,
     "Requires approved TikTok Research API access. No scraping is performed."),
    ("instagram", "Instagram Graph API", "unsupported", None, "SOCIAL", "Instagram", [], [], 0.5, False,
     "Requires Meta app review / business account credentials. No scraping is performed."),
    ("x_twitter", "X API", "unsupported", None, "SOCIAL", "X/Twitter", [], [], 0.5, False, "Requires paid X API credentials."),
    ("google_trends", "Google Trends", "unsupported", None, "SEARCH", "Google Trends", [], [], 0.7, False,
     "No official public API. Relative index only; adapter pending a permitted access method."),
    ("demo_fixture", "DEMO / TEST FIXTURE (not live data)", "fixture", None, "EDITORIAL", "Fixture",
     [], [], 0.5, False, "Synthetic records for testing and UI demo. Every record it creates is flagged is_fixture=true."),
]

DEFAULT_WEIGHTS = {
    "weights.trend.default": {"social": 25, "search": 20, "editorial": 15, "retail": 20, "velocity": 15, "diversity": 5},
    "weights.early.default": {"velocity": 20, "acceleration": 25, "search_growth": 20, "diversity": 15, "engagement": 10, "retail": 10},
    "weights.opportunity.default": {"source_momentum": 20, "target_early_growth": 20, "market_gap": 20, "search_acceleration": 15,
                                    "retail_gap": 10, "multi_market": 10, "freshness": 5},
    "thresholds": {"min_independent_sources": 2, "min_coverage_for_status": 0.2, "early_min_history_days": 7, "early_min_mentions": 5},
    "opportunity.presets": [{"name": "Asia → US", "source_markets": ["JP", "KR", "VN"], "target_market": "US"}],
    "export": {"image_mode": "url", "include_headers": True},
    "scheduler": {"timezone": "Asia/Ho_Chi_Minh"},
    "ui": {"theme": "light", "language": "vi"},
}


def seed(db: Session) -> None:
    ind_by_name: dict[str, Industry] = {i.name: i for i in db.scalars(select(Industry))}
    first_run = not ind_by_name
    if first_run:
        for order, (iname, spec) in enumerate(INDUSTRIES.items()):
            ind = Industry(name=iname, sort_order=order, aliases=[])
            db.add(ind)
            db.flush()
            ind_by_name[iname] = ind
            for key, label, ident in spec["attrs"]:
                db.add(ProductAttributeDefinition(industry_id=ind.id, key=key, label=label, identity_relevant=ident))
            for cname, c in spec["cats"].items():
                cat = Category(industry_id=ind.id, name=cname, keywords=c["kw"], local_keywords=c["local"], brands=c.get("brands", []))
                db.add(cat)
                db.flush()
                for sname, brands in c["subs"].items():
                    db.add(Category(industry_id=ind.id, parent_id=cat.id, name=sname, brands=brands, keywords=[sname]))
        db.flush()

    existing_brands = {b.name for b in db.scalars(select(Brand))}
    for name, aliases, domains, inds in BRANDS:
        if name not in existing_brands:
            db.add(Brand(name=name, aliases=aliases, official_domains=domains,
                         industry_ids=[ind_by_name[i].id for i in inds if i in ind_by_name]))

    existing_markets = {m.code for m in db.scalars(select(Market))}
    for code, name, region, langs, gn, is_city, parent in MARKETS:
        if code not in existing_markets:
            db.add(Market(code=code, name=name, region=region, languages=langs, is_city=is_city, parent_code=parent,
                          google_news_ceid="|".join(gn) if gn else None))

    existing_sources = {s.key for s in db.scalars(select(Source))}
    for key, name, adapter, url, stype, platform, inds, markets, cred, enabled, notes in SOURCES:
        if key not in existing_sources:
            db.add(Source(key=key, name=name, adapter=adapter, url=url, source_type=stype, platform=platform,
                          industry_ids=[ind_by_name[i].id for i in inds if i in ind_by_name], markets=markets,
                          credibility=cred, enabled=enabled, is_fixture=(adapter == "fixture"),
                          requires_credentials=adapter in ("youtube", "unsupported"),
                          credential_env="YOUTUBE_API_KEY" if adapter == "youtube" else None,
                          status="NOT_CONFIGURED" if adapter == "unsupported" else "UNTESTED", notes=notes))

    existing_settings = {s.key for s in db.scalars(select(Setting))}
    for k, v in DEFAULT_WEIGHTS.items():
        if k not in existing_settings:
            db.add(Setting(key=k, value=v))

    if first_run and not db.scalars(select(ScanPreset)).first():
        def cat_ids(*names: str) -> list[int]:
            return [c.id for c in db.scalars(select(Category).where(Category.name.in_(names)))]
        db.add_all([
            ScanPreset(name="US Sneakers (example)", markets=["US"], category_ids=cat_ids("Air Jordan", "Nike", "Adidas"),
                       priority="P1", mode="DISCOVERY", depth="QUICK"),
            ScanPreset(name="Asia Electronics (example)", markets=["JP", "KR", "VN"],
                       category_ids=cat_ids("Headphones & Earbuds", "AI Gadgets"), priority="P2"),
            ScanPreset(name="Global Collectibles (example)", markets=["US", "JP", "GB", "DE"], category_ids=cat_ids("LEGO", "Figures"), priority="P2"),
            ScanPreset(name="Beauty Research (example)", markets=["US", "KR"], category_ids=cat_ids("Skincare", "Makeup"), priority="P3"),
        ])
    db.flush()
    upgrade_seed(db)
    upgrade_seed_v3(db)
    upgrade_seed_v4(db)
    upgrade_seed_v5(db)


# ---------------------------------------------------------------- versioned upgrades for existing databases
# Each step runs once (tracked in settings 'seed.version'); it only ADDS defaults and never removes user data.
EXTRA_ALIASES = {
    "Apple": ["iPhone", "iPad", "AirPods", "MacBook", "Apple Watch", "Vision Pro"],
    "Google": ["Pixel", "Google Pixel", "Nest"],
    "Sony": ["PlayStation"],
    "Xiaomi": ["Redmi", "POCO"],
    "Nintendo": ["Switch 2"],
}
SOURCES_V2 = [
    # key, name, adapter, url, type, platform, industries, markets, credibility, enabled, notes
    ("hypebeast_jp", "Hypebeast Japan", "rss", "https://hypebeast.com/jp/feed", "EDITORIAL", "Hypebeast JP",
     ["Fashion & Footwear", "Toys & Collectibles"], ["JP"], 0.8, True, "Japanese edition feed (URL not verified from the build environment - press Test)."),
    ("hypebeast_kr", "Hypebeast Korea", "rss", "https://hypebeast.kr/feed", "EDITORIAL", "Hypebeast KR",
     ["Fashion & Footwear", "Toys & Collectibles"], ["KR"], 0.8, True, "Korean edition feed (URL not verified - press Test)."),
    ("itmedia", "ITmedia (all news)", "rss", "https://rss.itmedia.co.jp/rss/2.0/itmedia_all.xml", "EDITORIAL", "ITmedia",
     ["Electronics & Technology"], ["JP"], 0.8, True, "Japanese tech news (URL not verified - press Test)."),
    ("gizmodo_jp", "Gizmodo Japan", "rss", "https://www.gizmodo.jp/index.xml", "EDITORIAL", "Gizmodo JP",
     ["Electronics & Technology"], ["JP"], 0.75, True, "Japanese gadget news (URL not verified - press Test)."),
    ("vnexpress_sohoa", "VnExpress Số hóa", "rss", "https://vnexpress.net/rss/so-hoa.rss", "EDITORIAL", "VnExpress",
     ["Electronics & Technology"], ["VN"], 0.8, True, "Vietnamese tech news (URL not verified - press Test)."),
    ("reddit_gadgets", "Reddit r/gadgets (RSS)", "rss", "https://www.reddit.com/r/gadgets/.rss", "SOCIAL", "Reddit",
     ["Electronics & Technology"], ["GLOBAL"], 0.5, True, "Public subreddit RSS, no account. May be RATE_LIMITED."),
    ("manual_capture", "Manual capture (pages you browsed)", "manual", None, "SOCIAL", "Manual",
     [], [], 0.6, True, "Filled from the bookmarklet / Add Evidence page while YOU browse as a normal visitor. Never crawled automatically."),
]


def upgrade_seed(db: Session) -> None:
    row = db.get(Setting, "seed.version")
    version = int(row.value) if row else 1
    if version < 2:
        for b in db.scalars(select(Brand)):
            extra = EXTRA_ALIASES.get(b.name)
            if extra:
                b.aliases = list(dict.fromkeys(list(b.aliases or []) + extra))
        ind_by_name = {i.name: i for i in db.scalars(select(Industry))}
        existing = {s.key: s for s in db.scalars(select(Source))}
        for key, name, adapter, url, stype, platform, inds, markets, cred, enabled, notes in SOURCES_V2:
            if key in existing:
                continue
            db.add(Source(key=key, name=name, adapter=adapter, url=url, source_type=stype, platform=platform,
                          industry_ids=[ind_by_name[i].id for i in inds if i in ind_by_name], markets=markets, credibility=cred,
                          enabled=enabled, status="MANUAL" if adapter == "manual" else "UNTESTED", notes=notes))
        if "reddit_sneakers" in existing and existing["reddit_sneakers"].status == "UNTESTED":
            existing["reddit_sneakers"].enabled = True
        gt = existing.get("google_trends")
        if gt is not None:
            gt.adapter, gt.enabled, gt.status = "trends_import", True, "MANUAL_IMPORT"
            gt.notes = ("No official public API. Download 'Interest over time' CSV on trends.google.com while browsing normally, "
                        "then import it on the Add Evidence & Imports page. Relative 0-100 index only.")
        if row is None:
            db.add(Setting(key="seed.version", value=2))
        else:
            row.value = 2
    db.flush()


# v3: much larger brand dictionary (+ Japanese/Korean/Vietnamese spellings) - extraction only recognises known brands
BRANDS_V3 = {
    "Fashion & Footwear": [
        ("Onitsuka Tiger", []), ("Reebok", []), ("Mizuno", []), ("Saucony", []), ("Brooks", ["Brooks Running"]),
        ("Under Armour", []), ("Timberland", []), ("Dr. Martens", ["Dr Martens"]), ("Crocs", []), ("Birkenstock", []),
        ("UGG", []), ("Stüssy", ["Stussy"]), ("Carhartt WIP", ["Carhartt"]), ("The North Face", ["TNF"]), ("Arc'teryx", ["Arcteryx"]),
        ("Patagonia", []), ("Uniqlo", ["UNIQLO"]), ("Zara", []), ("BAPE", ["A Bathing Ape"]), ("Kith", []),
        ("Fear of God", ["Fear of God Essentials"]), ("Off-White", []), ("Louis Vuitton", []), ("Gucci", []),
        ("Prada", []), ("Balenciaga", []), ("Maison Margiela", ["Margiela"]), ("MSCHF", []), ("Converse", []),
        ("Vans", []), ("Supreme", []), ("Palace", ["Palace Skateboards"]), ("Corteiz", []), ("Hoka", ["HOKA"]),
    ],
    "Electronics & Technology": [
        ("Huawei", ["HUAWEI"]), ("OPPO", ["Oppo"]), ("vivo", ["Vivo"]), ("Honor", ["HONOR"]), ("Realme", ["realme"]),
        ("Garmin", []), ("DJI", []), ("Insta360", []), ("GoPro", []), ("Meta", ["Meta Quest", "Ray-Ban Meta"]),
        ("Microsoft", ["Xbox", "Surface"]), ("ASUS", ["ROG", "Asus"]), ("Lenovo", ["Legion", "ThinkPad"]), ("Valve", ["Steam Deck"]),
        ("Razer", []), ("Marshall", []), ("JBL", []), ("Sennheiser", []), ("Beats", ["Beats by Dre"]), ("Fitbit", []),
        ("Amazon", ["Kindle", "Echo", "Fire TV"]), ("Nvidia", ["NVIDIA", "GeForce"]), ("AMD", ["Ryzen", "Radeon"]),
        ("Keychron", []), ("Shokz", []), ("Ugreen", ["UGREEN"]), ("Baseus", []), ("Ecovacs", []), ("Roborock", []),
    ],
    "Beauty & Personal Care": [
        ("The Ordinary", []), ("Anua", []), ("Beauty of Joseon", []), ("Rare Beauty", []), ("Fenty Beauty", ["Fenty"]),
        ("Glossier", []), ("Torriden", []), ("Medicube", []), ("Innisfree", []), ("La Roche-Posay", ["La Roche Posay"]),
        ("CeraVe", []), ("Estée Lauder", ["Estee Lauder"]), ("Dior", ["Dior Beauty"]), ("Chanel", []), ("YSL Beauty", ["YSL"]),
        ("Sulwhasoo", []), ("Skin1004", ["SKIN1004"]), ("Round Lab", []), ("Some By Mi", []), ("Romand", ["rom&nd"]),
        ("Shiseido", []), ("Anessa", []), ("Biore", ["Bioré"]), ("Drunk Elephant", []), ("Sol de Janeiro", []),
    ],
    "Toys & Collectibles": [
        ("Hot Wheels", []), ("Funko", ["Funko Pop"]), ("Pokémon", ["Pokemon", "Pokémon TCG", "Pokemon TCG"]), ("Tamagotchi", []),
        ("Sylvanian Families", ["Calico Critters"]), ("Jellycat", []), ("Sonny Angel", []), ("Smiski", []), ("Hasbro", []),
        ("Mattel", []), ("Medicom Toy", ["Bearbrick", "BE@RBRICK"]), ("Good Smile", ["Nendoroid", "Good Smile Company"]),
        ("Hot Toys", []), ("Mega Bloks", []),
    ],
    "Home & Living": [("Stanley", ["Stanley Quencher"]), ("Owala", []), ("Ninja", ["Ninja Creami"]), ("Le Creuset", []),
                      ("IKEA", []), ("Yeti", ["YETI"]), ("Hydro Flask", []), ("Philips", []), ("Xiaomi Mijia", ["Mijia"])],
}
LOCAL_ALIASES_V3 = {  # local-script spellings used by JP / KR / VN / CN sources
    "Nike": ["ナイキ", "나이키"], "adidas": ["アディダス", "아디다스"], "New Balance": ["ニューバランス", "뉴발란스"],
    "ASICS": ["アシックス", "아식스"], "Apple": ["アップル", "애플"], "Sony": ["ソニー", "소니"], "Samsung": ["삼성", "サムスン"],
    "Xiaomi": ["小米"], "Pop Mart": ["泡泡玛特", "ポップマート", "팝마트"], "LEGO": ["レゴ", "레고"], "Nintendo": ["任天堂", "닌텐도"],
    "Air Jordan": ["エアジョーダン", "에어조던"], "Onitsuka Tiger": ["オニツカタイガー"], "Uniqlo": ["ユニクロ", "유니클로"],
}


def upgrade_seed_v3(db: Session) -> None:
    row = db.get(Setting, "seed.version")
    if row is None or int(row.value) >= 3:
        return
    inds = {i.name: i.id for i in db.scalars(select(Industry))}
    existing = {b.name.lower(): b for b in db.scalars(select(Brand))}
    for ind_name, items in BRANDS_V3.items():
        for name, aliases in items:
            if name.endswith(" x"):
                continue
            b = existing.get(name.lower())
            if b is None:
                b = Brand(name=name, aliases=aliases, official_domains=[], industry_ids=[inds[ind_name]] if ind_name in inds else [])
                db.add(b)
                existing[name.lower()] = b
            else:
                b.aliases = list(dict.fromkeys(list(b.aliases or []) + aliases))
    for name, aliases in LOCAL_ALIASES_V3.items():
        b = existing.get(name.lower())
        if b is not None:
            b.aliases = list(dict.fromkeys(list(b.aliases or []) + aliases))
    row.value = 3
    db.flush()


# v4: more specialist publisher feeds (product-level headlines). URLs not verifiable from the build environment.
SOURCES_V4 = [
    ("kicksonfire", "KicksOnFire", "https://www.kicksonfire.com/feed/", ["Fashion & Footwear"], ["US"]),
    ("highsnobiety", "Highsnobiety", "https://www.highsnobiety.com/feed/", ["Fashion & Footwear"], ["GLOBAL"]),
    ("footwearnews", "Footwear News", "https://footwearnews.com/feed/", ["Fashion & Footwear"], ["US"]),
    ("macrumors", "MacRumors", "https://feeds.macrumors.com/MacRumors-All", ["Electronics & Technology"], ["GLOBAL"]),
    ("9to5google", "9to5Google", "https://9to5google.com/feed/", ["Electronics & Technology"], ["GLOBAL"]),
    ("androidauthority", "Android Authority", "https://www.androidauthority.com/feed/", ["Electronics & Technology"], ["GLOBAL"]),
    ("androidpolice", "Android Police", "https://www.androidpolice.com/feed/", ["Electronics & Technology"], ["GLOBAL"]),
    ("tomsguide", "Tom's Guide", "https://www.tomsguide.com/feeds/all", ["Electronics & Technology", "Home & Living"], ["US"]),
    ("techcrunch_gadgets", "TechCrunch Gadgets", "https://techcrunch.com/category/gadgets/feed/", ["Electronics & Technology"], ["US"]),
    ("theverge_tech", "The Verge Tech", "https://www.theverge.com/rss/tech/index.xml", ["Electronics & Technology"], ["US"]),
    ("engadget_deals", "Engadget Deals", "https://www.engadget.com/deals/rss.xml", ["Electronics & Technology", "Home & Living"], ["US"]),
]


def upgrade_seed_v4(db: Session) -> None:
    row = db.get(Setting, "seed.version")
    if row is None or int(row.value) >= 4:
        return
    inds = {i.name: i.id for i in db.scalars(select(Industry))}
    existing = {s.key for s in db.scalars(select(Source))}
    for key, name, url, ind_names, markets in SOURCES_V4:
        if key not in existing:
            db.add(Source(key=key, name=name, adapter="rss", url=url, source_type="EDITORIAL", platform=name,
                          industry_ids=[inds[i] for i in ind_names if i in inds], markets=markets, credibility=0.75,
                          enabled=True, status="UNTESTED", notes="Publisher feed added in v0.7 (URL not verified - press Test)."))
    row.value = 4
    db.flush()


# v5 (app v0.9): sneaker research channels the user follows
SOURCES_V5 = [
    # key, name, adapter, url, markets, credibility, notes
    ("sneakerbardetroit", "Sneaker Bar Detroit", "rss", "https://sneakerbardetroit.com/feed/", ["GLOBAL"], 0.75,
     "WordPress feed (pages 2-5 read automatically)."),
    ("justfreshkicks", "JustFreshKicks", "rss", "https://justfreshkicks.com/feed/", ["GLOBAL"], 0.7,
     "WordPress feed (URL not verified from the build environment - press Test)."),
    ("houseofheat", "House of Heat", "rss", "https://houseofheat.co/feed", ["GLOBAL"], 0.75,
     "Feed URL not verified from the build environment - press Test. If it fails, use the bookmarklet while reading the site."),
    ("complex_sneakers", "Complex Sneakers", "rss", "https://www.complex.com/sneakers/rss", ["GLOBAL"], 0.75,
     "Complex has no documented public feed; this URL may fail - press Test. If it fails, use the bookmarklet."),
    ("hypebeast_footwear", "Hypebeast Footwear", "rss", "https://hypebeast.com/footwear/feed", ["GLOBAL"], 0.8,
     "Footwear-only section feed (more sneaker articles than the general Hypebeast feed)."),
    ("sbd_jordan_calendar", "SBD Air Jordan release calendar", "release_calendar",
     "https://sneakerbardetroit.com/air-jordan-release-dates/", ["US"], 0.7,
     "Release-date page (no feed). Each entry: name, colorway, style code, date, US price. Filed as REPORTED / EXPECTED."),
    ("sbd_sneaker_calendar", "SBD sneaker release calendar", "release_calendar",
     "https://sneakerbardetroit.com/sneaker-release-dates/", ["US"], 0.7,
     "All-brand release-date page (no feed). Same parser as the Air Jordan calendar."),
]


def upgrade_seed_v5(db: Session) -> None:
    row = db.get(Setting, "seed.version")
    if row is None or int(row.value) >= 5:
        return
    inds = {i.name: i.id for i in db.scalars(select(Industry))}
    existing = {s.key for s in db.scalars(select(Source))}
    fashion = [inds["Fashion & Footwear"]] if "Fashion & Footwear" in inds else []
    for key, name, adapter, url, markets, cred, notes in SOURCES_V5:
        if key not in existing:
            db.add(Source(key=key, name=name, adapter=adapter, url=url, source_type="EDITORIAL", platform=name,
                          industry_ids=fashion, markets=markets, credibility=cred, enabled=True, status="UNTESTED",
                          notes=notes))
    row.value = 5
    db.flush()
