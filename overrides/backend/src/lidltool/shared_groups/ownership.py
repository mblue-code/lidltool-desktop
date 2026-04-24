from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, false, or_
from sqlalchemy.sql.elements import ColumnElement

from lidltool.analytics.scope import VisibilityContext


@dataclass(frozen=True, slots=True)
class WorkspaceOwner:
    user_id: str | None
    shared_group_id: str | None
    workspace_kind: str


def owner_from_visibility(visibility: VisibilityContext) -> WorkspaceOwner:
    if visibility.workspace_kind == "shared_group" and visibility.shared_group_id:
        return WorkspaceOwner(
            user_id=visibility.user_id,
            shared_group_id=visibility.shared_group_id,
            workspace_kind="shared_group",
        )
    return WorkspaceOwner(
        user_id=visibility.user_id,
        shared_group_id=None,
        workspace_kind="personal",
    )


def assign_owner(
    record: Any,
    *,
    visibility: VisibilityContext,
    user_id: str | None = None,
) -> None:
    owner = owner_from_visibility(visibility)
    if hasattr(record, "shared_group_id"):
        record.shared_group_id = owner.shared_group_id
    if hasattr(record, "user_id") and user_id is not None:
        record.user_id = user_id


def ownership_filter(
    model: Any,
    *,
    visibility: VisibilityContext,
    include_service_unowned: bool = False,
) -> ColumnElement[bool]:
    user_column = getattr(model, "user_id", None)
    shared_group_column = getattr(model, "shared_group_id", None)
    if user_column is None and shared_group_column is None:
        return false()

    if visibility.workspace_kind == "shared_group" and visibility.shared_group_id and shared_group_column is not None:
        return shared_group_column == visibility.shared_group_id

    if shared_group_column is not None:
        clauses: list[ColumnElement[bool]] = [shared_group_column.is_(None)]
        if user_column is not None:
            if visibility.is_service and include_service_unowned:
                clauses.append(or_(user_column == visibility.user_id, user_column.is_(None)))
            else:
                clauses.append(user_column == visibility.user_id)
        return and_(*clauses)

    if user_column is None:
        return false()
    if visibility.is_service and include_service_unowned:
        return or_(user_column == visibility.user_id, user_column.is_(None))
    return user_column == visibility.user_id


def resource_belongs_to_workspace(
    *,
    visibility: VisibilityContext,
    resource_user_id: str | None,
    resource_shared_group_id: str | None,
) -> bool:
    if visibility.workspace_kind == "shared_group" and visibility.shared_group_id:
        return resource_shared_group_id == visibility.shared_group_id
    if resource_shared_group_id is not None:
        return False
    if visibility.is_service:
        return resource_user_id in {None, visibility.user_id}
    return resource_user_id == visibility.user_id
