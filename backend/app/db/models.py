"""SQLAlchemy ORM models — all tables in one file for clarity."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, ForeignKey,
    Integer, String, Text, UniqueConstraint, JSON,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


def _uuid():
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Multi-tenant
# ---------------------------------------------------------------------------

class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name = Column(String(200), nullable=False)
    slug = Column(String(100), nullable=False, unique=True)
    is_active = Column(Boolean, default=True)
    max_meta_accounts = Column(Integer, default=15)
    created_at = Column(DateTime, default=datetime.utcnow)

    users = relationship("User", back_populates="tenant", lazy="selectin")
    meta_accounts = relationship("MetaAccount", back_populates="tenant", lazy="selectin")


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    email = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    name = Column(String(200))
    role = Column(Enum("admin", "manager", "viewer", name="user_role"), default="viewer")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    tenant = relationship("Tenant", back_populates="users")

    __table_args__ = (UniqueConstraint("tenant_id", "email"),)


# ---------------------------------------------------------------------------
# Meta Ads accounts
# ---------------------------------------------------------------------------

class MetaAccount(Base):
    __tablename__ = "meta_accounts"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    ad_account_id = Column(String(100), nullable=False)
    name = Column(String(200))
    access_token = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    last_synced_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    tenant = relationship("Tenant", back_populates="meta_accounts")
    campaigns = relationship("Campaign", back_populates="meta_account", lazy="dynamic")

    __table_args__ = (UniqueConstraint("tenant_id", "ad_account_id"),)


# ---------------------------------------------------------------------------
# Campaigns / AdSets / Ads
# ---------------------------------------------------------------------------

class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    meta_account_id = Column(UUID(as_uuid=False), ForeignKey("meta_accounts.id"), nullable=False)
    meta_campaign_id = Column(String(100), nullable=False, unique=True)
    name = Column(String(500))
    objective = Column(String(100))
    status = Column(String(50))
    daily_budget = Column(Float)
    lifetime_budget = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    meta_account = relationship("MetaAccount", back_populates="campaigns")
    adsets = relationship("AdSet", back_populates="campaign", lazy="dynamic")


class AdSet(Base):
    __tablename__ = "adsets"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    campaign_id = Column(UUID(as_uuid=False), ForeignKey("campaigns.id"), nullable=False)
    meta_adset_id = Column(String(100), nullable=False, unique=True)
    name = Column(String(500))
    status = Column(String(50))
    daily_budget = Column(Float)
    targeting = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    campaign = relationship("Campaign", back_populates="adsets")
    ads = relationship("Ad", back_populates="adset", lazy="dynamic")


class Ad(Base):
    __tablename__ = "ads"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    adset_id = Column(UUID(as_uuid=False), ForeignKey("adsets.id"), nullable=False)
    meta_ad_id = Column(String(100), nullable=False, unique=True)
    name = Column(String(500))
    status = Column(String(50))
    creative_id = Column(String(100))
    creative_type = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    adset = relationship("AdSet", back_populates="ads")
    metrics = relationship("AdMetric", back_populates="ad", lazy="dynamic")


# ---------------------------------------------------------------------------
# Metrics snapshots
# ---------------------------------------------------------------------------

class AdMetric(Base):
    __tablename__ = "ad_metrics"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    ad_id = Column(UUID(as_uuid=False), ForeignKey("ads.id"), nullable=False)
    date = Column(DateTime, nullable=False)
    impressions = Column(Integer, default=0)
    clicks = Column(Integer, default=0)
    spend = Column(Float, default=0.0)
    conversions = Column(Integer, default=0)
    revenue = Column(Float, default=0.0)
    ctr = Column(Float)
    cpc = Column(Float)
    cpm = Column(Float)
    cpa = Column(Float)
    roas = Column(Float)
    frequency = Column(Float)
    reach = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    ad = relationship("Ad", back_populates="metrics")

    __table_args__ = (UniqueConstraint("ad_id", "date"),)


# ---------------------------------------------------------------------------
# Agent events & actions
# ---------------------------------------------------------------------------

class AgentEvent(Base):
    __tablename__ = "agent_events"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    event_type = Column(String(100), nullable=False)
    entity_type = Column(String(50))
    entity_id = Column(String(100))
    payload = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)


class AgentAction(Base):
    __tablename__ = "agent_actions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    action_type = Column(String(100), nullable=False)
    entity_type = Column(String(50))
    entity_id = Column(String(100))
    payload = Column(JSON)
    status = Column(Enum("pending", "executed", "failed", "skipped", name="action_status"), default="pending")
    executed_at = Column(DateTime)
    error = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class Diagnosis(Base):
    __tablename__ = "diagnoses"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    entity_type = Column(String(50))
    entity_id = Column(String(100))
    issue_type = Column(String(100), nullable=False)
    severity = Column(Enum("low", "medium", "high", "critical", name="severity_level"), default="medium")
    details = Column(JSON)
    resolved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class WhatsAppReport(Base):
    __tablename__ = "whatsapp_reports"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    phone_number = Column(String(30), nullable=False)
    report_type = Column(String(100))
    content = Column(Text)
    status = Column(Enum("sent", "failed", "pending", name="report_status"), default="pending")
    sent_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    agent_name = Column(String(50), nullable=False)
    trigger = Column(String(20), nullable=False, default="scheduled")
    status = Column(String(20), nullable=False, default="running")
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)
    duration_seconds = Column(Float)
    items_processed = Column(Integer)
    error = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class AgentInsight(Base):
    __tablename__ = "agent_insights"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=False), ForeignKey("tenants.id"))
    agent_name = Column(String(50), nullable=False)
    title = Column(Text, nullable=False)
    summary = Column(Text, nullable=False)
    details = Column(JSON)
    actions_taken = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
