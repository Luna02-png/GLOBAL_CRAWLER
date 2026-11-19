"""Canonical data model. Raw observations (evidence, signals) are stored separately from derived scores
so scores can always be recomputed when weights or algorithms change."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, utcnow


# ---------------------------------------------------------------- taxonomy
class Industry(Base):
    __tablename__ = "industries"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    categories: Mapped[list["Category"]] = relationship(back_populates="industry")


class Category(Base):
    """Category or subcategory (parent_id set => subcategory)."""
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    industry_id: Mapped[int] = mapped_column(ForeignKey("industries.id"))
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    exclude_keywords: Mapped[list] = mapped_column(JSON, default=list)
    local_keywords: Mapped[dict] = mapped_column(JSON, default=dict)  # {"ja": [...], "vi": [...]}
    brands: Mapped[list] = mapped_column(JSON, default=list)
    preferred_sources: Mapped[list] = mapped_column(JSON, default=list)
    group_label: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    industry: Mapped[Industry] = relationship(back_populates="categories")
    __table_args__ = (UniqueConstraint("industry_id", "parent_id", "name", name="uq_category_name"),)


class ProductAttributeDefinition(Base):
    __tablename__ = "product_attribute_definitions"
    id: Mapped[int] = mapped_column(primary_key=True)
    industry_id: Mapped[int] = mapped_column(ForeignKey("industries.id"))
    key: Mapped[str] = mapped_column(String(100))
    label: Mapped[str] = mapped_column(String(200))
    identity_relevant: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("industry_id", "key"),)


class Brand(Base):
    """Brand dictionary used by entity extraction. Editable by the user."""
    __tablename__ = "brands"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    official_domains: Mapped[list] = mapped_column(JSON, default=list)
    industry_ids: Mapped[list] = mapped_column(JSON, default=list)


# ---------------------------------------------------------------- markets
class Market(Base):
    __tablename__ = "markets"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)  # US, JP, VN, US-NYC
    name: Mapped[str] = mapped_column(String(200))
    region: Mapped[str] = mapped_column(String(100))
    languages: Mapped[list] = mapped_column(JSON, default=list)
    is_city: Mapped[bool] = mapped_column(Boolean, default=False)
    parent_code: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    google_news_ceid: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)  # e.g. JP:ja
    active: Mapped[bool] = mapped_column(Boolean, default=True)


# ---------------------------------------------------------------- products
class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_key: Mapped[str] = mapped_column(String(400), unique=True)
    brand: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    name: Mapped[str] = mapped_column(String(400))
    model_variant: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    sku: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    release_status: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    is_fixture: Mapped[bool] = mapped_column(Boolean, default=False)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    first_detected: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    link_status: Mapped[str] = mapped_column(String(40), default="NOT_CHECKED")
    link_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    __table_args__ = (Index("ix_products_brand_name", "brand", "name"),)


class ProductAlias(Base):
    __tablename__ = "product_aliases"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    alias: Mapped[str] = mapped_column(String(400))
    lang: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    __table_args__ = (UniqueConstraint("product_id", "alias"),)


class ProductCategory(Base):
    __tablename__ = "product_categories"
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ProductMarket(Base):
    """Geographic attribution supported by evidence."""
    __tablename__ = "product_markets"
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)
    market_code: Mapped[str] = mapped_column(String(40), primary_key=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    attribution: Mapped[str] = mapped_column(String(60), default="SOURCE_EDITION")
    confidence: Mapped[str] = mapped_column(String(20), default="MEDIUM")


# ---------------------------------------------------------------- sources
class Source(Base):
    __tablename__ = "source_registry"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    adapter: Mapped[str] = mapped_column(String(50))  # rss | google_news | fixture
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(40), default="EDITORIAL")  # EDITORIAL/SOCIAL/RETAIL/SEARCH/OFFICIAL
    platform: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    industry_ids: Mapped[list] = mapped_column(JSON, default=list)  # empty = all
    markets: Mapped[list] = mapped_column(JSON, default=list)  # markets this source edition represents
    credibility: Mapped[float] = mapped_column(Float, default=0.7)
    requires_credentials: Mapped[bool] = mapped_column(Boolean, default=False)
    credential_env: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_fixture: Mapped[bool] = mapped_column(Boolean, default=False)
    rate_per_minute: Mapped[int] = mapped_column(Integer, default=20)
    concurrency: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(30), default="NOT_CONFIGURED")
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_checked: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_success: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    cooldown_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    etag: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_modified: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    source_key: Mapped[str] = mapped_column(String(100))
    source_type: Mapped[str] = mapped_column(String(40))
    platform: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    outlet: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # independent outlet identity
    url: Mapped[str] = mapped_column(Text)
    url_is_aggregator: Mapped[bool] = mapped_column(Boolean, default=False)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    snippet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    author: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    lang: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    market_code: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, index=True)
    claim_type: Mapped[str] = mapped_column(String(40), default="MENTION")
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    engagement: Mapped[dict] = mapped_column(JSON, default=dict)  # only observed values
    content_fingerprint: Mapped[str] = mapped_column(String(64), index=True)  # syndication dedup
    is_syndicated_copy: Mapped[bool] = mapped_column(Boolean, default=False)
    is_fixture: Mapped[bool] = mapped_column(Boolean, default=False)
    job_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    __table_args__ = (UniqueConstraint("product_id", "url", name="uq_evidence_product_url"),)


class ProductLink(Base):
    __tablename__ = "product_links"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(Text)
    page_type: Mapped[str] = mapped_column(String(40))
    source: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    market_code: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    identity_match: Mapped[str] = mapped_column(String(30))
    info_fields: Mapped[dict] = mapped_column(JSON, default=dict)
    completeness_score: Mapped[float] = mapped_column(Float, default=0)
    is_primary_information_url: Mapped[bool] = mapped_column(Boolean, default=False)
    is_purchase_url: Mapped[bool] = mapped_column(Boolean, default=False)
    user_selected: Mapped[bool] = mapped_column(Boolean, default=False)
    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    stock_state: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    accessible: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    fetch_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    first_found_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    provenance: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_fixture: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("product_id", "url", name="uq_link_product_url"),)


# ---------------------------------------------------------------- scans
class ScanPreset(Base):
    __tablename__ = "scan_presets"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    markets: Mapped[list] = mapped_column(JSON, default=list)
    category_ids: Mapped[list] = mapped_column(JSON, default=list)
    industry_ids: Mapped[list] = mapped_column(JSON, default=list)
    include_keywords: Mapped[list] = mapped_column(JSON, default=list)
    exclude_keywords: Mapped[list] = mapped_column(JSON, default=list)
    local_aliases: Mapped[dict] = mapped_column(JSON, default=dict)
    source_keys: Mapped[list] = mapped_column(JSON, default=list)  # empty = all applicable
    source_priorities: Mapped[dict] = mapped_column(JSON, default=dict)
    priority: Mapped[str] = mapped_column(String(4), default="P3")  # P1 / P2 / P3
    mode: Mapped[str] = mapped_column(String(20), default="DISCOVERY")  # DISCOVERY / TRACKING
    depth: Mapped[str] = mapped_column(String(10), default="QUICK")  # QUICK / FULL
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    schedule_time: Mapped[str] = mapped_column(String(5), default="07:00")
    schedule_weekday: Mapped[int] = mapped_column(Integer, default=0)  # 0 = Monday (for P2)
    limits: Mapped[dict] = mapped_column(JSON, default=dict)
    export_columns: Mapped[list] = mapped_column(JSON, default=list)
    last_success_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    schedule_anchor_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)  # reset when priority/time changes
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)


class ScanJob(Base):
    __tablename__ = "scan_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))  # SCAN / LINK_FINDER
    preset_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    preset_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    trigger: Mapped[str] = mapped_column(String(20))  # SCHEDULED / MANUAL / CATCHUP
    mode: Mapped[str] = mapped_column(String(20), default="DISCOVERY")
    depth: Mapped[str] = mapped_column(String(10), default="QUICK")
    scope: Mapped[dict] = mapped_column(JSON, default=dict)
    priority: Mapped[int] = mapped_column(Integer, default=50)  # lower runs first
    dedup_key: Mapped[Optional[str]] = mapped_column(String(300), nullable=True, unique=True)
    status: Mapped[str] = mapped_column(String(20), default="QUEUED")
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    checkpoint: Mapped[dict] = mapped_column(JSON, default=dict)
    current_source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    worker_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    heartbeat_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    __table_args__ = (Index("ix_jobs_status_priority", "status", "priority", "created_at"),)


class ScanTask(Base):
    __tablename__ = "scan_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("scan_jobs.id", ondelete="CASCADE"), index=True)
    source_key: Mapped[str] = mapped_column(String(100))
    market_code: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    category_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    query: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    work_key: Mapped[str] = mapped_column(String(400))
    status: Mapped[str] = mapped_column(String(20), default="QUEUED")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    items_found: Mapped[int] = mapped_column(Integer, default=0)
    products_new: Mapped[int] = mapped_column(Integer, default=0)
    products_updated: Mapped[int] = mapped_column(Integer, default=0)
    from_cache: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class FetchCache(Base):
    __tablename__ = "fetch_cache"
    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(Text, unique=True)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status_code: Mapped[int] = mapped_column(Integer)
    etag: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_modified: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ---------------------------------------------------------------- signals & scores
class MarketSignalCoverage(Base):
    """Which (market, category, source) combinations were actually scanned successfully - lets us
    distinguish 'not observed despite coverage' from 'never looked'."""
    __tablename__ = "market_signal_coverage"
    id: Mapped[int] = mapped_column(primary_key=True)
    market_code: Mapped[str] = mapped_column(String(40))
    category_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_key: Mapped[str] = mapped_column(String(100))
    source_type: Mapped[str] = mapped_column(String(40))
    last_success_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    successful_scans: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (UniqueConstraint("market_code", "category_id", "source_key"),)


class ProductDailySignal(Base):
    __tablename__ = "product_daily_signal_metrics"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    market_code: Mapped[str] = mapped_column(String(40))
    day: Mapped[date] = mapped_column(Date)
    mentions: Mapped[int] = mapped_column(Integer, default=0)
    independent_sources: Mapped[int] = mapped_column(Integer, default=0)
    engagement_total: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    retail_signals: Mapped[int] = mapped_column(Integer, default=0)
    search_index: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    __table_args__ = (UniqueConstraint("product_id", "market_code", "day"),)


class ProductMarketTrend(Base):
    __tablename__ = "product_market_trends"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    market_code: Mapped[str] = mapped_column(String(40))
    trend_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    trend_status: Mapped[str] = mapped_column(String(30))
    breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[str] = mapped_column(String(20))
    coverage: Mapped[float] = mapped_column(Float, default=0)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    early_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lifecycle_stage: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    early_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    early_provisional: Mapped[bool] = mapped_column(Boolean, default=True)
    early_explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("product_id", "market_code"),)


class TrendHistory(Base):
    __tablename__ = "trend_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    market_code: Mapped[str] = mapped_column(String(40))
    trend_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    trend_status: Mapped[str] = mapped_column(String(30))
    early_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lifecycle_stage: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    job_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class UpcomingRelease(Base):
    __tablename__ = "upcoming_releases"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    market_code: Mapped[str] = mapped_column(String(40))
    expected_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    expected_date_text: Mapped[str] = mapped_column(String(60), default="TBA")
    date_precision: Mapped[str] = mapped_column(String(20), default="TBA")  # DAY/MONTH/QUARTER/SEASON/YEAR/TBA
    release_status: Mapped[str] = mapped_column(String(30))
    rumor_confidence: Mapped[str] = mapped_column(String(20), default="UNVERIFIED")
    hype_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    expected_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    source_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    first_reported: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_updated: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    latest_development: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    __table_args__ = (UniqueConstraint("product_id", "market_code"),)


class ReleaseHistory(Base):
    __tablename__ = "release_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    release_id: Mapped[int] = mapped_column(ForeignKey("upcoming_releases.id", ondelete="CASCADE"))
    field: Mapped[str] = mapped_column(String(60))
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class OpportunityScore(Base):
    __tablename__ = "opportunity_scores"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    source_markets: Mapped[list] = mapped_column(JSON, default=list)
    target_market: Mapped[str] = mapped_column(String(40))
    preset_key: Mapped[str] = mapped_column(String(200))
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    opportunity_type: Mapped[str] = mapped_column(String(40))
    breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[str] = mapped_column(String(20))
    coverage: Mapped[float] = mapped_column(Float, default=0)
    risk_level: Mapped[str] = mapped_column(String(20))
    target_data_state: Mapped[str] = mapped_column(String(40))
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("product_id", "preset_key"),)


class Shortlist(Base):
    __tablename__ = "shortlists"
    id: Mapped[int] = mapped_column(primary_key=True)
    list_type: Mapped[str] = mapped_column(String(30))  # EARLY_WATCHLIST / OPPORTUNITY
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    target_market: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    priority: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    research_status: Mapped[str] = mapped_column(String(40), default="Researching")
    supplier_check: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    marketing_test_status: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("list_type", "product_id", "target_market"),)


class ChangeEvent(Base):
    __tablename__ = "change_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    product_id: Mapped[Optional[int]] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=True)
    market_code: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    job_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_fixture: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)


class SearchInterest(Base):
    """Relative search-interest index (0-100) imported from a Google Trends CSV the user downloaded.
    Values are relative to the term/geo/period of that export and never treated as absolute volume."""
    __tablename__ = "search_interest"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    market_code: Mapped[str] = mapped_column(String(40))
    term: Mapped[str] = mapped_column(String(300))
    day: Mapped[date] = mapped_column(Date)
    value: Mapped[float] = mapped_column(Float)
    granularity: Mapped[str] = mapped_column(String(10))  # DAY / WEEK / MONTH
    source_file: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("product_id", "market_code", "term", "day", name="uq_search_point"),)
