from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from lidltool.db.models import Source, SourceAccount

OCR_SOURCE_ID = "ocr_upload"


def ensure_ocr_source(
    session: Session,
    *,
    owner_user_id: str | None,
) -> tuple[Source, SourceAccount]:
    source = session.get(Source, OCR_SOURCE_ID)
    if source is None:
        source = Source(
            id=OCR_SOURCE_ID,
            user_id=owner_user_id,
            kind="ocr",
            display_name="OCR Uploads",
            status="healthy",
            enabled=True,
        )
        session.add(source)
        session.flush()
    elif source.user_id is None and owner_user_id is not None:
        source.user_id = owner_user_id

    account = session.execute(
        select(SourceAccount).where(SourceAccount.source_id == source.id).limit(1)
    ).scalar_one_or_none()
    if account is None:
        account = SourceAccount(source_id=source.id, account_ref="default", status="connected")
        session.add(account)
        session.flush()
    return source, account

