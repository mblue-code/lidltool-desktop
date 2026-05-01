from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


class Store(Base):
    __tablename__ = "stores"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    address: Mapped[str | None] = mapped_column(String, nullable=True)

    receipts: Mapped[list[Receipt]] = relationship(back_populates="store")


class Receipt(Base):
    __tablename__ = "receipts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    purchased_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    store_id: Mapped[str | None] = mapped_column(ForeignKey("stores.id"), nullable=True, index=True)
    store_name: Mapped[str | None] = mapped_column(String, nullable=True)
    store_address: Mapped[str | None] = mapped_column(String, nullable=True)
    total_gross: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(8), default="EUR")
    discount_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    raw_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)

    store: Mapped[Store | None] = relationship(back_populates="receipts")
    items: Mapped[list[ReceiptItem]] = relationship(
        back_populates="receipt", cascade="all, delete-orphan"
    )


class ReceiptItem(Base):
    __tablename__ = "receipt_items"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    receipt_id: Mapped[str] = mapped_column(ForeignKey("receipts.id"), index=True)
    line_no: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(Text)
    qty: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    unit: Mapped[str | None] = mapped_column(String, nullable=True)
    unit_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    line_total: Mapped[int] = mapped_column(Integer)
    vat_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    discounts: Mapped[list[dict[str, object]] | None] = mapped_column(JSON, nullable=True)

    receipt: Mapped[Receipt] = relationship(back_populates="items")


Index("ix_receipt_items_name", ReceiptItem.name)
Index("ix_receipt_items_category", ReceiptItem.category)
Index("ux_receipt_items_receipt_line", ReceiptItem.receipt_id, ReceiptItem.line_no, unique=True)


class SyncState(Base):
    __tablename__ = "sync_state"

    source: Mapped[str] = mapped_column(String, primary_key=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_receipt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_seen_receipt_id: Mapped[str | None] = mapped_column(String, nullable=True)


class CategoryRule(Base):
    __tablename__ = "category_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pattern: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100)


class FinanceCategoryRule(Base):
    __tablename__ = "finance_category_rules"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    rule_type: Mapped[str] = mapped_column(String, nullable=False, default="merchant")
    pattern: Mapped[str] = mapped_column(String, nullable=False, index=True)
    normalized_pattern: Mapped[str] = mapped_column(String, nullable=False, index=True)
    category_id: Mapped[str] = mapped_column(ForeignKey("categories.category_id"), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(16), nullable=False, default="outflow", index=True)
    source: Mapped[str] = mapped_column(String, nullable=False, default="learned")
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Category(Base):
    __tablename__ = "categories"

    category_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    parent_category_id: Mapped[str | None] = mapped_column(
        ForeignKey("categories.category_id"), nullable=True, index=True
    )


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    username: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    preferred_locale: Mapped[str | None] = mapped_column(String(8), nullable=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    sources: Mapped[list[Source]] = relationship(back_populates="user")
    transactions: Mapped[list[Transaction]] = relationship(back_populates="user")
    api_keys: Mapped[list[UserApiKey]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    sessions: Mapped[list[UserSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    mobile_devices: Mapped[list[MobileDevice]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    chat_threads: Mapped[list[ChatThread]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    recurring_bills: Mapped[list[RecurringBill]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    budget_rules: Mapped[list[BudgetRule]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    budget_months: Mapped[list[BudgetMonth]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    cashflow_entries: Mapped[list[CashflowEntry]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    goals: Mapped[list[Goal]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    notifications: Mapped[list[Notification]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    offer_source_configs: Mapped[list[OfferSourceConfig]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    shared_group_memberships: Mapped[list[SharedGroupMember]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    created_shared_groups: Mapped[list[SharedGroup]] = relationship(
        back_populates="created_by_user"
    )


class UserApiKey(Base):
    __tablename__ = "user_api_keys"

    key_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.user_id"), nullable=True, index=True)
    label: Mapped[str] = mapped_column(String, nullable=False)
    key_prefix: Mapped[str] = mapped_column(String, nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="api_keys")


class UserSession(Base):
    __tablename__ = "user_sessions"

    session_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.user_id"), nullable=True, index=True
    )
    device_label: Mapped[str | None] = mapped_column(String, nullable=True)
    client_name: Mapped[str | None] = mapped_column(String, nullable=True)
    client_platform: Mapped[str | None] = mapped_column(String, nullable=True)
    auth_transport: Mapped[str] = mapped_column(String, nullable=False, default="cookie")
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_seen_ip: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    revoked_reason: Mapped[str | None] = mapped_column(String, nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")
    mobile_devices: Mapped[list[MobileDevice]] = relationship(back_populates="session_record")


class MobileDevice(Base):
    __tablename__ = "mobile_devices"

    device_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("user_sessions.session_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    installation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    client_platform: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    push_provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    push_token: Mapped[str] = mapped_column(Text, nullable=False)
    device_label: Mapped[str | None] = mapped_column(String, nullable=True)
    client_name: Mapped[str | None] = mapped_column(String, nullable=True)
    app_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    locale: Mapped[str | None] = mapped_column(String(8), nullable=True)
    notifications_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True
    )
    last_registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_push_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_push_error_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_push_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    user: Mapped[User] = relationship(back_populates="mobile_devices")
    session_record: Mapped[UserSession | None] = relationship(back_populates="mobile_devices")


Index("ux_mobile_devices_user_installation", MobileDevice.user_id, MobileDevice.installation_id, unique=True)
Index("ix_mobile_devices_provider_token", MobileDevice.push_provider, MobileDevice.push_token)


class MobilePairingSession(Base):
    __tablename__ = "mobile_pairing_sessions"

    session_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    desktop_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    desktop_name: Mapped[str] = mapped_column(String, nullable=False)
    endpoint_url: Mapped[str] = mapped_column(Text, nullable=False)
    pairing_token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    public_key_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True, index=True
    )
    paired_device_id: Mapped[str | None] = mapped_column(String, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class MobilePairedDevice(Base):
    __tablename__ = "mobile_paired_devices"

    paired_device_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    desktop_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    device_name: Mapped[str | None] = mapped_column(String, nullable=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    sync_token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    public_key_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    protocol_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


Index(
    "ux_mobile_paired_devices_desktop_device",
    MobilePairedDevice.desktop_id,
    MobilePairedDevice.device_id,
    unique=True,
)


class MobileCapture(Base):
    __tablename__ = "mobile_captures"

    capture_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    paired_device_id: Mapped[str] = mapped_column(
        ForeignKey("mobile_paired_devices.paired_device_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    mobile_capture_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id"), nullable=True, index=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("ingestion_jobs.id"), nullable=True, index=True)
    file_name: Mapped[str | None] = mapped_column(String, nullable=True)
    mime_type: Mapped[str] = mapped_column(String, nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="uploaded", index=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


Index(
    "ux_mobile_captures_device_capture",
    MobileCapture.paired_device_id,
    MobileCapture.mobile_capture_id,
    unique=True,
)


class ChatThread(Base):
    __tablename__ = "chat_threads"

    thread_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), nullable=False, index=True)
    shared_group_id: Mapped[str | None] = mapped_column(
        ForeignKey("shared_groups.group_id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String, nullable=False, default="New chat")
    stream_status: Mapped[str] = mapped_column(String, nullable=False, default="idle")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="chat_threads")
    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="thread", cascade="all, delete-orphan"
    )
    runs: Mapped[list[ChatRun]] = relationship(back_populates="thread", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    message_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    thread_id: Mapped[str] = mapped_column(ForeignKey("chat_threads.thread_id"), index=True)
    role: Mapped[str] = mapped_column(String, nullable=False)
    content_json: Mapped[dict[str, object] | list[dict[str, object]]] = mapped_column(
        JSON, nullable=False
    )
    tool_name: Mapped[str | None] = mapped_column(String, nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(String, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String, nullable=True)
    usage_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    thread: Mapped[ChatThread] = relationship(back_populates="messages")
    runs: Mapped[list[ChatRun]] = relationship(back_populates="message")


Index("ix_chat_messages_thread_created", ChatMessage.thread_id, ChatMessage.created_at)
Index("ix_chat_messages_thread_message", ChatMessage.thread_id, ChatMessage.message_id)
Index(
    "ux_chat_messages_thread_idempotency",
    ChatMessage.thread_id,
    ChatMessage.idempotency_key,
    unique=True,
)


class ChatRun(Base):
    __tablename__ = "chat_runs"

    run_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    thread_id: Mapped[str] = mapped_column(ForeignKey("chat_threads.thread_id"), index=True)
    message_id: Mapped[str | None] = mapped_column(
        ForeignKey("chat_messages.message_id"), nullable=True, index=True
    )
    model_id: Mapped[str] = mapped_column(String, nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="ok")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    thread: Mapped[ChatThread] = relationship(back_populates="runs")
    message: Mapped[ChatMessage | None] = relationship(back_populates="runs")


class SharedGroup(Base):
    __tablename__ = "shared_groups"

    group_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String, nullable=False)
    group_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active", index=True)
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    memberships: Mapped[list[SharedGroupMember]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )
    created_by_user: Mapped[User | None] = relationship(back_populates="created_shared_groups")


class SharedGroupMember(Base):
    __tablename__ = "shared_group_members"

    group_id: Mapped[str] = mapped_column(
        ForeignKey("shared_groups.group_id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String, nullable=False, default="member", index=True)
    membership_status: Mapped[str] = mapped_column(
        String, nullable=False, default="active", index=True
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    group: Mapped[SharedGroup] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="shared_group_memberships")


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.user_id"), nullable=True)
    shared_group_id: Mapped[str | None] = mapped_column(
        ForeignKey("shared_groups.group_id"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    reporting_role: Mapped[str] = mapped_column(String, nullable=False, default="spending_and_cashflow")
    status: Mapped[str] = mapped_column(String, nullable=False, default="healthy")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    user: Mapped[User | None] = relationship(back_populates="sources")
    accounts: Mapped[list[SourceAccount]] = relationship(back_populates="source")
    transactions: Mapped[list[Transaction]] = relationship(back_populates="source")


class SourceAccount(Base):
    __tablename__ = "source_accounts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    account_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="connected")
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    source: Mapped[Source] = relationship(back_populates="accounts")
    jobs: Mapped[list[IngestionJob]] = relationship(back_populates="source_account")


class ConnectorLifecycleState(Base):
    __tablename__ = "connector_lifecycle_state"

    source_id: Mapped[str] = mapped_column(String, primary_key=True)
    plugin_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    install_origin: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    installed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    desired_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ConnectorConfigState(Base):
    __tablename__ = "connector_config_state"

    source_id: Mapped[str] = mapped_column(String, primary_key=True)
    plugin_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    public_config_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    secret_config_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    source_account_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_accounts.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued")
    trigger_type: Mapped[str] = mapped_column(String, nullable=False, default="manual")
    idempotency_key: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    source_account: Mapped[SourceAccount | None] = relationship(back_populates="jobs")


class IngestionSession(Base):
    __tablename__ = "ingestion_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.user_id"), nullable=True, index=True)
    shared_group_id: Mapped[str | None] = mapped_column(
        ForeignKey("shared_groups.group_id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String, nullable=False, default="Ingestion session")
    input_kind: Mapped[str] = mapped_column(String, nullable=False, default="free_text", index=True)
    approval_mode: Mapped[str] = mapped_column(String, nullable=False, default="review_first")
    status: Mapped[str] = mapped_column(String, nullable=False, default="draft", index=True)
    summary_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    files: Mapped[list[IngestionFile]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    rows: Mapped[list[StatementRow]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    proposals: Mapped[list[IngestionProposal]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class IngestionAgentSettings(Base):
    __tablename__ = "ingestion_agent_settings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.user_id"), nullable=True, index=True)
    shared_group_id: Mapped[str | None] = mapped_column(
        ForeignKey("shared_groups.group_id"), nullable=True, index=True
    )
    approval_mode: Mapped[str] = mapped_column(String, nullable=False, default="review_first")
    auto_commit_confidence_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.95)
    auto_link_confidence_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.98)
    auto_ignore_confidence_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.98)
    auto_create_recurring_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    personal_system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class IngestionFile(Base):
    __tablename__ = "ingestion_files"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(
        ForeignKey("ingestion_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str | None] = mapped_column(String, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String, nullable=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped[IngestionSession] = relationship(back_populates="files")
    rows: Mapped[list[StatementRow]] = relationship(back_populates="file")


class StatementRow(Base):
    __tablename__ = "statement_rows"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(
        ForeignKey("ingestion_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_id: Mapped[str | None] = mapped_column(
        ForeignKey("ingestion_files.id", ondelete="SET NULL"), nullable=True, index=True
    )
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    booked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payee: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="EUR")
    raw_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="parsed", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    session: Mapped[IngestionSession] = relationship(back_populates="rows")
    file: Mapped[IngestionFile | None] = relationship(back_populates="rows")
    proposals: Mapped[list[IngestionProposal]] = relationship(back_populates="statement_row")


class IngestionProposal(Base):
    __tablename__ = "ingestion_proposals"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(
        ForeignKey("ingestion_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    statement_row_id: Mapped[str | None] = mapped_column(
        ForeignKey("statement_rows.id", ondelete="SET NULL"), nullable=True, index=True
    )
    type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending_review", index=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    payload_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_metadata_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    commit_result_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    session: Mapped[IngestionSession] = relationship(back_populates="proposals")
    statement_row: Mapped[StatementRow | None] = relationship(back_populates="proposals")
    matches: Mapped[list[IngestionProposalMatch]] = relationship(
        back_populates="proposal", cascade="all, delete-orphan"
    )


class IngestionProposalMatch(Base):
    __tablename__ = "ingestion_proposal_matches"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    proposal_id: Mapped[str] = mapped_column(
        ForeignKey("ingestion_proposals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"), nullable=False, index=True)
    score: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    reason_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    proposal: Mapped[IngestionProposal] = relationship(back_populates="matches")
    transaction: Mapped[Transaction] = relationship()


Index("ix_ingestion_sessions_user_status", IngestionSession.user_id, IngestionSession.status)
Index("ux_ingestion_agent_settings_scope", IngestionAgentSettings.user_id, IngestionAgentSettings.shared_group_id, unique=True)
Index("ix_ingestion_files_session_sha", IngestionFile.session_id, IngestionFile.sha256)
Index("ux_statement_rows_session_hash", StatementRow.session_id, StatementRow.row_hash, unique=True)
Index("ix_ingestion_proposals_session_status", IngestionProposal.session_id, IngestionProposal.status)
Index("ix_ingestion_proposals_session_type", IngestionProposal.session_id, IngestionProposal.type)


class ConnectorPayloadQuarantine(Base):
    __tablename__ = "connector_payload_quarantine"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), nullable=False, index=True)
    source_account_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_accounts.id"), nullable=True, index=True
    )
    ingestion_job_id: Mapped[str | None] = mapped_column(
        ForeignKey("ingestion_jobs.id"), nullable=True, index=True
    )
    plugin_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    manifest_version: Mapped[str | None] = mapped_column(String, nullable=True)
    connector_api_version: Mapped[str | None] = mapped_column(String, nullable=True)
    runtime_kind: Mapped[str | None] = mapped_column(String, nullable=True)
    action_name: Mapped[str] = mapped_column(String, nullable=False)
    outcome: Mapped[str] = mapped_column(String, nullable=False, index=True)
    review_status: Mapped[str] = mapped_column(String, nullable=False, default="pending", index=True)
    source_record_ref: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    payload_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    validation_errors: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    runtime_diagnostics: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.user_id"), nullable=True)
    shared_group_id: Mapped[str | None] = mapped_column(
        ForeignKey("shared_groups.group_id"), nullable=True, index=True
    )
    source_account_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_accounts.id"), nullable=True, index=True
    )
    source_transaction_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    purchased_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    merchant_name: Mapped[str | None] = mapped_column(String, nullable=True)
    total_gross_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False, default="outflow", index=True)
    ledger_scope: Mapped[str] = mapped_column(String(32), nullable=False, default="household", index=True)
    dashboard_include: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="EUR")
    discount_total_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    direction: Mapped[str] = mapped_column(String, nullable=False, default="outflow", index=True)
    finance_category_id: Mapped[str | None] = mapped_column(
        ForeignKey("categories.category_id"), nullable=True, index=True
    )
    finance_category_method: Mapped[str | None] = mapped_column(String, nullable=True)
    finance_category_confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(4, 3), nullable=True
    )
    finance_category_source_value: Mapped[str | None] = mapped_column(String, nullable=True)
    finance_category_version: Mapped[str | None] = mapped_column(String, nullable=True)
    finance_tags_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    raw_payload: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    source: Mapped[Source] = relationship(back_populates="transactions")
    user: Mapped[User | None] = relationship(back_populates="transactions")
    items: Mapped[list[TransactionItem]] = relationship(
        back_populates="transaction", cascade="all, delete-orphan"
    )
    discount_events: Mapped[list[DiscountEvent]] = relationship(
        back_populates="transaction", cascade="all, delete-orphan"
    )
    documents: Mapped[list[Document]] = relationship(back_populates="transaction")
    recurring_matches: Mapped[list[RecurringBillMatch]] = relationship(
        back_populates="transaction", cascade="all, delete-orphan"
    )


class TransactionItem(Base):
    __tablename__ = "transaction_items"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"), index=True)
    shared_group_id: Mapped[str | None] = mapped_column(
        ForeignKey("shared_groups.group_id"), nullable=True, index=True
    )
    source_item_id: Mapped[str | None] = mapped_column(String, nullable=True)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    unit: Mapped[str | None] = mapped_column(String, nullable=True)
    unit_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    line_total_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    category_id: Mapped[str | None] = mapped_column(
        ForeignKey("categories.category_id"), nullable=True, index=True
    )
    category_method: Mapped[str | None] = mapped_column(String, nullable=True)
    category_confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(4, 3), nullable=True
    )
    category_source_value: Mapped[str | None] = mapped_column(String, nullable=True)
    category_version: Mapped[str | None] = mapped_column(String, nullable=True)
    product_id: Mapped[str | None] = mapped_column(
        ForeignKey("products.product_id"), nullable=True, index=True
    )
    is_deposit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    raw_payload: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)

    transaction: Mapped[Transaction] = relationship(back_populates="items")
    discount_events: Mapped[list[DiscountEvent]] = relationship(back_populates="transaction_item")
    product: Mapped[Product | None] = relationship(back_populates="items")


class RecurringBill(Base):
    __tablename__ = "recurring_bills"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), nullable=False, index=True)
    shared_group_id: Mapped[str | None] = mapped_column(
        ForeignKey("shared_groups.group_id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    merchant_canonical: Mapped[str | None] = mapped_column(String, nullable=True)
    merchant_alias_pattern: Mapped[str | None] = mapped_column(String, nullable=True)
    category: Mapped[str] = mapped_column(String, nullable=False, default="uncategorized")
    frequency: Mapped[str] = mapped_column(String, nullable=False, default="monthly")
    interval_value: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount_tolerance_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.1)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="EUR")
    anchor_date: Mapped[str] = mapped_column(String(10), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    user: Mapped[User] = relationship(back_populates="recurring_bills")
    occurrences: Mapped[list[RecurringBillOccurrence]] = relationship(
        back_populates="bill", cascade="all, delete-orphan"
    )


class RecurringBillOccurrence(Base):
    __tablename__ = "recurring_bill_occurrences"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    bill_id: Mapped[str] = mapped_column(
        ForeignKey("recurring_bills.id", ondelete="CASCADE"), nullable=False, index=True
    )
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="upcoming")
    expected_amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    bill: Mapped[RecurringBill] = relationship(back_populates="occurrences")
    matches: Mapped[list[RecurringBillMatch]] = relationship(
        back_populates="occurrence", cascade="all, delete-orphan"
    )


class RecurringBillMatch(Base):
    __tablename__ = "recurring_bill_matches"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    occurrence_id: Mapped[str] = mapped_column(
        ForeignKey("recurring_bill_occurrences.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    transaction_id: Mapped[str] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    match_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    match_method: Mapped[str] = mapped_column(String, nullable=False, default="manual")
    matched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    occurrence: Mapped[RecurringBillOccurrence] = relationship(back_populates="matches")
    transaction: Mapped[Transaction] = relationship(back_populates="recurring_matches")


Index("idx_sources_user_id", Source.user_id)
Index("idx_transactions_user_id", Transaction.user_id)
Index("idx_user_api_keys_user_id", UserApiKey.user_id)
Index("idx_user_api_keys_active", UserApiKey.is_active)
Index("ix_user_sessions_user_created", UserSession.user_id, UserSession.created_at)
Index("ix_shared_groups_type_status", SharedGroup.group_type, SharedGroup.status)
Index("ix_shared_groups_creator", SharedGroup.created_by_user_id, SharedGroup.created_at)
Index(
    "ix_shared_group_members_user_status",
    SharedGroupMember.user_id,
    SharedGroupMember.membership_status,
)
Index("ix_recurring_bills_user_active", RecurringBill.user_id, RecurringBill.active)
Index("ix_recurring_bills_group_active", RecurringBill.shared_group_id, RecurringBill.active)
Index(
    "ux_recurring_bill_occurrences_bill_due_date",
    RecurringBillOccurrence.bill_id,
    RecurringBillOccurrence.due_date,
    unique=True,
)
Index(
    "ux_recurring_bill_matches_occurrence_transaction",
    RecurringBillMatch.occurrence_id,
    RecurringBillMatch.transaction_id,
    unique=True,
)


class DiscountEvent(Base):
    __tablename__ = "discount_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"), index=True)
    transaction_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("transaction_items.id"), nullable=True, index=True
    )
    source: Mapped[str] = mapped_column(String, nullable=False)
    source_discount_code: Mapped[str | None] = mapped_column(String, nullable=True)
    source_label: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(String, nullable=False, default="item")
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="EUR")
    kind: Mapped[str] = mapped_column(String, nullable=False, default="unknown")
    subkind: Mapped[str | None] = mapped_column(String, nullable=True)
    funded_by: Mapped[str] = mapped_column(String, nullable=False, default="unknown")
    is_loyalty_program: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    raw_payload: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)

    transaction: Mapped[Transaction] = relationship(back_populates="discount_events")
    transaction_item: Mapped[TransactionItem | None] = relationship(
        back_populates="discount_events"
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    transaction_id: Mapped[str | None] = mapped_column(
        ForeignKey("transactions.id"), nullable=True, index=True
    )
    source_id: Mapped[str | None] = mapped_column(
        ForeignKey("sources.id"), nullable=True, index=True
    )
    shared_group_id: Mapped[str | None] = mapped_column(
        ForeignKey("shared_groups.group_id"), nullable=True, index=True
    )
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(String, nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    file_name: Mapped[str | None] = mapped_column(String, nullable=True)
    ocr_status: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    review_status: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    ocr_provider: Mapped[str | None] = mapped_column(String, nullable=True)
    ocr_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ocr_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    ocr_fallback_used: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    transaction: Mapped[Transaction | None] = relationship(back_populates="documents")


class MerchantAlias(Base):
    __tablename__ = "merchant_aliases"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    alias: Mapped[str] = mapped_column(String, nullable=False, index=True)
    canonical_name: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class NormalizationRule(Base):
    __tablename__ = "normalization_rules"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    rule_type: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    pattern: Mapped[str] = mapped_column(String, nullable=False)
    replacement: Mapped[str | None] = mapped_column(String, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class AutomationRule(Base):
    __tablename__ = "automation_rules"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String, nullable=False)
    rule_type: Mapped[str] = mapped_column(String, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    trigger_config: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    action_config: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    executions: Mapped[list[AutomationExecution]] = relationship(
        back_populates="rule", cascade="all, delete-orphan"
    )


class AutomationExecution(Base):
    __tablename__ = "automation_executions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    rule_id: Mapped[str] = mapped_column(ForeignKey("automation_rules.id"), index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="success")
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    rule: Mapped[AutomationRule] = relationship(back_populates="executions")


Index("ix_automation_rules_enabled_rule_type", AutomationRule.enabled, AutomationRule.rule_type)
Index("ix_automation_rules_next_run_at", AutomationRule.next_run_at)
Index(
    "ix_automation_executions_rule_id_triggered_at",
    AutomationExecution.rule_id,
    AutomationExecution.triggered_at,
)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    actor_type: Mapped[str] = mapped_column(String, nullable=False, default="system")
    actor_id: Mapped[str | None] = mapped_column(String, nullable=True)
    action: Mapped[str] = mapped_column(String, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String, nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    details: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EndpointMetric(Base):
    __tablename__ = "endpoint_metrics"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    route: Mapped[str] = mapped_column(String, nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class IncidentEvent(Base):
    __tablename__ = "incident_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    incident_key: Mapped[str] = mapped_column(String, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String, nullable=False, default="sev3")
    source: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    details: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class RecoveryDrillEvidence(Base):
    __tablename__ = "recovery_drill_evidence"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    drill_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String, nullable=False, index=True)
    artifact_path: Mapped[str] = mapped_column(Text, nullable=False)
    elapsed_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    rto_target_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    rpo_target_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    rto_target_met: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rpo_target_met: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class TrainingHint(Base):
    __tablename__ = "training_hints"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    transaction_id: Mapped[str] = mapped_column(
        ForeignKey("transactions.id"), nullable=False, index=True
    )
    transaction_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("transaction_items.id"), nullable=True, index=True
    )
    hint_type: Mapped[str] = mapped_column(String, nullable=False)
    field_path: Mapped[str] = mapped_column(String, nullable=False)
    original_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrected_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Product(Base):
    __tablename__ = "products"

    product_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    brand: Mapped[str | None] = mapped_column(String, nullable=True)
    default_unit: Mapped[str | None] = mapped_column(String, nullable=True)
    category_id: Mapped[str | None] = mapped_column(
        ForeignKey("categories.category_id"), nullable=True, index=True
    )
    gtin_ean: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    is_ai_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cluster_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    aliases: Mapped[list[ProductAlias]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    items: Mapped[list[TransactionItem]] = relationship(back_populates="product")


class ProductAlias(Base):
    __tablename__ = "product_aliases"

    alias_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    product_id: Mapped[str] = mapped_column(ForeignKey("products.product_id"), index=True)
    source_kind: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_name: Mapped[str] = mapped_column(Text, nullable=False)
    raw_sku: Mapped[str | None] = mapped_column(String, nullable=True)
    match_confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False, default=1)
    match_method: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    product: Mapped[Product] = relationship(back_populates="aliases")


Index("idx_product_aliases_raw", ProductAlias.source_kind, ProductAlias.raw_name)


class OfferSourceConfig(Base):
    __tablename__ = "offer_source_configs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    shared_group_id: Mapped[str | None] = mapped_column(
        ForeignKey("shared_groups.group_id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_id: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    merchant_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    merchant_url: Mapped[str] = mapped_column(Text, nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False, default="DE")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    user: Mapped[User] = relationship(back_populates="offer_source_configs")


class OfferSource(Base):
    __tablename__ = "offer_sources"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    plugin_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    merchant_name: Mapped[str] = mapped_column(String, nullable=False)
    merchant_id: Mapped[str | None] = mapped_column(String, nullable=True)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False, index=True)
    region_code: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    store_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    store_name: Mapped[str | None] = mapped_column(String, nullable=True)
    scope_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    raw_scope_payload: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    offers: Mapped[list[Offer]] = relationship(back_populates="offer_source")


class Offer(Base):
    __tablename__ = "offers"

    offer_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    offer_source_id: Mapped[str] = mapped_column(
        ForeignKey("offer_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plugin_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_offer_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    offer_type: Mapped[str] = mapped_column(String, nullable=False, default="unknown")
    status: Mapped[str] = mapped_column(String, nullable=False, default="active", index=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="EUR")
    price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    original_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discount_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    bundle_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    offer_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    validity_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    validity_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    raw_payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    normalized_payload: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    offer_source: Mapped[OfferSource] = relationship(back_populates="offers")
    items: Mapped[list[OfferItem]] = relationship(back_populates="offer", cascade="all, delete-orphan")
    matches: Mapped[list[OfferMatch]] = relationship(
        back_populates="offer", cascade="all, delete-orphan"
    )


class OfferItem(Base):
    __tablename__ = "offer_items"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    offer_id: Mapped[str] = mapped_column(
        ForeignKey("offers.offer_id", ondelete="CASCADE"), nullable=False, index=True
    )
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    source_item_id: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    brand: Mapped[str | None] = mapped_column(String, nullable=True)
    canonical_product_id: Mapped[str | None] = mapped_column(
        ForeignKey("products.product_id"), nullable=True, index=True
    )
    gtin_ean: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    alias_candidates: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    quantity_text: Mapped[str | None] = mapped_column(String, nullable=True)
    unit: Mapped[str | None] = mapped_column(String, nullable=True)
    size_text: Mapped[str | None] = mapped_column(String, nullable=True)
    price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    original_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discount_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    bundle_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    offer: Mapped[Offer] = relationship(back_populates="items")
    product: Mapped[Product | None] = relationship()
    matches: Mapped[list[OfferMatch]] = relationship(back_populates="offer_item")


Index("ux_offer_items_offer_line", OfferItem.offer_id, OfferItem.line_no, unique=True)


class ProductWatchlist(Base):
    __tablename__ = "product_watchlists"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), nullable=False, index=True)
    shared_group_id: Mapped[str | None] = mapped_column(
        ForeignKey("shared_groups.group_id"), nullable=True, index=True
    )
    product_id: Mapped[str | None] = mapped_column(
        ForeignKey("products.product_id"), nullable=True, index=True
    )
    query_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    min_discount_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    user: Mapped[User] = relationship()
    product: Mapped[Product | None] = relationship()
    matches: Mapped[list[OfferMatch]] = relationship(back_populates="watchlist")


class OfferMatch(Base):
    __tablename__ = "offer_matches"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    match_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    offer_id: Mapped[str] = mapped_column(
        ForeignKey("offers.offer_id", ondelete="CASCADE"), nullable=False, index=True
    )
    offer_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("offer_items.id", ondelete="CASCADE"), nullable=True, index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), nullable=False, index=True)
    shared_group_id: Mapped[str | None] = mapped_column(
        ForeignKey("shared_groups.group_id"), nullable=True, index=True
    )
    watchlist_id: Mapped[str | None] = mapped_column(
        ForeignKey("product_watchlists.id", ondelete="SET NULL"), nullable=True, index=True
    )
    matched_product_id: Mapped[str | None] = mapped_column(
        ForeignKey("products.product_id"), nullable=True, index=True
    )
    match_kind: Mapped[str] = mapped_column(String, nullable=False, index=True)
    match_method: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending_alert", index=True)
    reason_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    offer: Mapped[Offer] = relationship(back_populates="matches")
    offer_item: Mapped[OfferItem | None] = relationship(back_populates="matches")
    user: Mapped[User] = relationship()
    watchlist: Mapped[ProductWatchlist | None] = relationship(back_populates="matches")
    matched_product: Mapped[Product | None] = relationship()
    alert_events: Mapped[list[AlertEvent]] = relationship(
        back_populates="offer_match", cascade="all, delete-orphan"
    )


class AlertEvent(Base):
    __tablename__ = "alert_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), nullable=False, index=True)
    shared_group_id: Mapped[str | None] = mapped_column(
        ForeignKey("shared_groups.group_id"), nullable=True, index=True
    )
    offer_match_id: Mapped[str] = mapped_column(
        ForeignKey("offer_matches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False, default="offer_match", index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending", index=True)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    user: Mapped[User] = relationship()
    offer_match: Mapped[OfferMatch] = relationship(back_populates="alert_events")


class OfferRefreshRun(Base):
    __tablename__ = "offer_refresh_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.user_id"), nullable=True, index=True)
    shared_group_id: Mapped[str | None] = mapped_column(
        ForeignKey("shared_groups.group_id"), nullable=True, index=True
    )
    rule_id: Mapped[str | None] = mapped_column(
        ForeignKey("automation_rules.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    trigger_kind: Mapped[str] = mapped_column(String, nullable=False, default="manual")
    status: Mapped[str] = mapped_column(String, nullable=False, default="running", index=True)
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_ids_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    result_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    user: Mapped[User | None] = relationship()
    rule: Mapped[AutomationRule | None] = relationship()


class ComparisonGroup(Base):
    __tablename__ = "comparison_groups"

    group_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String, nullable=False)
    unit_standard: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    members: Mapped[list[ComparisonGroupMember]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )


class ComparisonGroupMember(Base):
    __tablename__ = "comparison_group_members"

    group_id: Mapped[str] = mapped_column(ForeignKey("comparison_groups.group_id"), primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.product_id"), primary_key=True)
    weight: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False, default=1)

    group: Mapped[ComparisonGroup] = relationship(back_populates="members")
    product: Mapped[Product] = relationship()


class SavedQuery(Base):
    __tablename__ = "saved_queries"

    query_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.user_id"), nullable=True, index=True)
    shared_group_id: Mapped[str | None] = mapped_column(
        ForeignKey("shared_groups.group_id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    query_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    is_preset: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ItemObservation(Base):
    __tablename__ = "item_observations"

    observation_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"), nullable=False, index=True)
    date: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), nullable=False, index=True)
    source_kind: Mapped[str] = mapped_column(String, nullable=False, index=True)
    product_id: Mapped[str | None] = mapped_column(
        ForeignKey("products.product_id"), nullable=True, index=True
    )
    raw_item_name: Mapped[str] = mapped_column(Text, nullable=False)
    quantity_value: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    quantity_unit: Mapped[str] = mapped_column(String, nullable=False)
    unit_price_gross_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_net_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total_gross_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total_net_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    basket_discount_alloc_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    category_id: Mapped[str | None] = mapped_column(
        ForeignKey("categories.category_id"), nullable=True, index=True
    )
    merchant_name: Mapped[str | None] = mapped_column(String, nullable=True)


Index("idx_obs_product_date", ItemObservation.product_id, ItemObservation.date)
Index("idx_obs_category_date", ItemObservation.category_id, ItemObservation.date)
Index("idx_obs_source_date", ItemObservation.source_kind, ItemObservation.date)
Index("idx_obs_date", ItemObservation.date)


class AnalyticsMetadata(Base):
    __tablename__ = "analytics_metadata"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class BudgetRule(Base):
    __tablename__ = "budget_rules"

    rule_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.user_id"), nullable=True, index=True
    )
    shared_group_id: Mapped[str | None] = mapped_column(
        ForeignKey("shared_groups.group_id"), nullable=True, index=True
    )
    scope_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    scope_value: Mapped[str] = mapped_column(String, nullable=False, index=True)
    period: Mapped[str] = mapped_column(String, nullable=False, default="monthly")
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="EUR")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    user: Mapped[User | None] = relationship(back_populates="budget_rules")


class BudgetMonth(Base):
    __tablename__ = "budget_months"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), nullable=False, index=True)
    shared_group_id: Mapped[str | None] = mapped_column(
        ForeignKey("shared_groups.group_id"), nullable=True, index=True
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    month: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    planned_income_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_savings_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    opening_balance_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="EUR")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    user: Mapped[User] = relationship(back_populates="budget_months")


class CashflowEntry(Base):
    __tablename__ = "cashflow_entries"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), nullable=False, index=True)
    shared_group_id: Mapped[str | None] = mapped_column(
        ForeignKey("shared_groups.group_id"), nullable=True, index=True
    )
    effective_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String, nullable=False, default="uncategorized")
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="EUR")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String, nullable=False, default="manual")
    linked_transaction_id: Mapped[str | None] = mapped_column(
        ForeignKey("transactions.id"), nullable=True, index=True
    )
    linked_recurring_occurrence_id: Mapped[str | None] = mapped_column(
        ForeignKey("recurring_bill_occurrences.id"), nullable=True, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    user: Mapped[User] = relationship(back_populates="cashflow_entries")


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    shared_group_id: Mapped[str | None] = mapped_column(
        ForeignKey("shared_groups.group_id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    goal_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    target_amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="EUR")
    period: Mapped[str] = mapped_column(String, nullable=False, default="current_window")
    category: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    merchant_name: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    recurring_bill_id: Mapped[str | None] = mapped_column(
        ForeignKey("recurring_bills.id"), nullable=True, index=True
    )
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    user: Mapped[User] = relationship(back_populates="goals")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    shared_group_id: Mapped[str | None] = mapped_column(
        ForeignKey("shared_groups.group_id", ondelete="SET NULL"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String, nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String, nullable=False, default="info", index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    href: Mapped[str | None] = mapped_column(String, nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    unread: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    user: Mapped[User] = relationship(back_populates="notifications")


Index("ix_budget_rules_user_active", BudgetRule.user_id, BudgetRule.active)
Index("ix_budget_rules_group_active", BudgetRule.shared_group_id, BudgetRule.active)
Index("ux_budget_months_user_period", BudgetMonth.user_id, BudgetMonth.year, BudgetMonth.month, unique=True)
Index(
    "ux_budget_months_group_period",
    BudgetMonth.shared_group_id,
    BudgetMonth.year,
    BudgetMonth.month,
    unique=True,
)
Index("ix_cashflow_entries_user_date", CashflowEntry.user_id, CashflowEntry.effective_date)
Index("ix_cashflow_entries_user_direction", CashflowEntry.user_id, CashflowEntry.direction)
Index("ix_cashflow_entries_group_date", CashflowEntry.shared_group_id, CashflowEntry.effective_date)
Index(
    "ix_cashflow_entries_group_direction",
    CashflowEntry.shared_group_id,
    CashflowEntry.direction,
)
Index("ix_goals_user_active", Goal.user_id, Goal.active)
Index("ix_goals_user_type", Goal.user_id, Goal.goal_type)
Index("ix_goals_group_active", Goal.shared_group_id, Goal.active)
Index("ix_goals_group_type", Goal.shared_group_id, Goal.goal_type)
Index("ix_notifications_user_unread", Notification.user_id, Notification.unread)
Index("ix_notifications_user_occurred", Notification.user_id, Notification.occurred_at)
Index("ix_notifications_group_unread", Notification.shared_group_id, Notification.unread)
Index("ix_notifications_group_occurred", Notification.shared_group_id, Notification.occurred_at)
Index("ux_notifications_user_fingerprint", Notification.user_id, Notification.fingerprint, unique=True)
Index(
    "ux_notifications_group_fingerprint",
    Notification.shared_group_id,
    Notification.fingerprint,
    unique=True,
)
