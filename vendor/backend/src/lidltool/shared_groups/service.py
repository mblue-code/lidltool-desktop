from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session, joinedload

from lidltool.auth.users import SERVICE_USERNAME
from lidltool.db.models import SharedGroup, SharedGroupMember, User

GROUP_TYPES = {"household", "community"}
GROUP_STATUSES = {"active", "archived"}
MEMBER_ROLES = {"owner", "manager", "member"}
MEMBERSHIP_STATUSES = {"active", "removed"}
_MANAGER_ROLES = {"owner", "manager"}


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def _normalize_required_text(value: str, *, field_name: str, max_length: int = 120) -> str:
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise ValueError(f"{field_name} is required")
    return normalized[:max_length]


def _normalize_choice(value: str, *, field_name: str, allowed: set[str]) -> str:
    normalized = value.strip().lower()
    if normalized not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        raise ValueError(f"{field_name} must be one of: {allowed_values}")
    return normalized


def _active_membership(
    session: Session,
    *,
    group_id: str,
    user_id: str,
) -> SharedGroupMember | None:
    return session.execute(
        select(SharedGroupMember)
        .where(
            SharedGroupMember.group_id == group_id,
            SharedGroupMember.user_id == user_id,
            SharedGroupMember.membership_status == "active",
        )
        .options(joinedload(SharedGroupMember.user))
    ).scalar_one_or_none()


def _require_group(session: Session, *, group_id: str) -> SharedGroup:
    group = session.execute(
        select(SharedGroup)
        .where(SharedGroup.group_id == group_id)
        .options(
            joinedload(SharedGroup.memberships).joinedload(SharedGroupMember.user),
            joinedload(SharedGroup.created_by_user),
        )
    ).unique().scalar_one_or_none()
    if group is None:
        raise ValueError("shared group not found")
    return group


def _require_membership(
    session: Session,
    *,
    group_id: str,
    user: User,
) -> SharedGroupMember:
    membership = _active_membership(session, group_id=group_id, user_id=user.user_id)
    if membership is None:
        raise ValueError("shared group not found")
    return membership


def _require_manager(
    session: Session,
    *,
    group_id: str,
    user: User,
) -> SharedGroupMember:
    membership = _require_membership(session, group_id=group_id, user=user)
    if membership.role not in _MANAGER_ROLES:
        raise ValueError("shared group management requires owner or manager role")
    return membership


def _serialize_user(user: User) -> dict[str, Any]:
    return {
        "user_id": user.user_id,
        "username": user.username,
        "display_name": user.display_name,
        "is_admin": user.is_admin,
        "preferred_locale": user.preferred_locale,
    }


def _serialize_group_member(member: SharedGroupMember) -> dict[str, Any]:
    return {
        "group_id": member.group_id,
        "user_id": member.user_id,
        "role": member.role,
        "membership_status": member.membership_status,
        "joined_at": member.joined_at.isoformat(),
        "created_at": member.created_at.isoformat(),
        "updated_at": member.updated_at.isoformat(),
        "user": _serialize_user(member.user),
    }


def _serialize_group(
    group: SharedGroup,
    *,
    viewer_membership: SharedGroupMember | None,
    include_members: bool,
) -> dict[str, Any]:
    owner_count = sum(
        1
        for member in group.memberships
        if member.membership_status == "active" and member.role == "owner"
    )
    result = {
        "group_id": group.group_id,
        "name": group.name,
        "group_type": group.group_type,
        "status": group.status,
        "created_at": group.created_at.isoformat(),
        "updated_at": group.updated_at.isoformat(),
        "created_by_user": _serialize_user(group.created_by_user) if group.created_by_user else None,
        "viewer_role": viewer_membership.role if viewer_membership is not None else None,
        "viewer_membership_status": (
            viewer_membership.membership_status if viewer_membership is not None else None
        ),
        "can_manage": viewer_membership is not None and viewer_membership.role in _MANAGER_ROLES,
        "owner_count": owner_count,
        "member_count": sum(1 for member in group.memberships if member.membership_status == "active"),
    }
    if include_members:
        result["members"] = [
            _serialize_group_member(member)
            for member in sorted(
                group.memberships,
                key=lambda value: (
                    0 if value.membership_status == "active" else 1,
                    0 if value.role == "owner" else 1 if value.role == "manager" else 2,
                    (value.user.display_name or value.user.username).lower(),
                ),
            )
        ]
    return result


def list_shared_group_user_directory(session: Session) -> dict[str, Any]:
    users = session.execute(
        select(User)
        .where(User.username != SERVICE_USERNAME)
        .order_by(User.is_admin.desc(), User.username.asc())
    ).scalars().all()
    items = [_serialize_user(user) for user in users]
    return {"count": len(items), "items": items, "users": items}


def list_shared_groups(session: Session, *, user: User) -> dict[str, Any]:
    groups = session.execute(
        select(SharedGroup)
        .join(SharedGroupMember, SharedGroupMember.group_id == SharedGroup.group_id)
        .where(
            SharedGroupMember.user_id == user.user_id,
            SharedGroupMember.membership_status == "active",
        )
        .options(
            joinedload(SharedGroup.memberships).joinedload(SharedGroupMember.user),
            joinedload(SharedGroup.created_by_user),
        )
        .order_by(SharedGroup.name.asc())
    ).unique().scalars().all()
    items = []
    for group in groups:
        viewer_membership = next(
            (member for member in group.memberships if member.user_id == user.user_id),
            None,
        )
        items.append(_serialize_group(group, viewer_membership=viewer_membership, include_members=True))
    return {"count": len(items), "items": items, "groups": items}


def get_shared_group_detail(session: Session, *, user: User, group_id: str) -> dict[str, Any]:
    group = _require_group(session, group_id=group_id)
    viewer_membership = _require_membership(session, group_id=group.group_id, user=user)
    return _serialize_group(group, viewer_membership=viewer_membership, include_members=True)


def create_shared_group(
    session: Session,
    *,
    creator: User,
    name: str,
    group_type: str,
) -> dict[str, Any]:
    group = SharedGroup(
        name=_normalize_required_text(name, field_name="name"),
        group_type=_normalize_choice(group_type, field_name="group_type", allowed=GROUP_TYPES),
        status="active",
        created_by_user_id=creator.user_id,
    )
    session.add(group)
    session.flush()
    membership = SharedGroupMember(
        group_id=group.group_id,
        user_id=creator.user_id,
        role="owner",
        membership_status="active",
        joined_at=_utcnow(),
    )
    session.add(membership)
    session.flush()
    group = _require_group(session, group_id=group.group_id)
    viewer_membership = _require_membership(session, group_id=group.group_id, user=creator)
    return _serialize_group(group, viewer_membership=viewer_membership, include_members=True)


def update_shared_group(
    session: Session,
    *,
    actor: User,
    group_id: str,
    name: str | None = None,
    group_type: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    membership = _require_manager(session, group_id=group_id, user=actor)
    group = _require_group(session, group_id=group_id)

    if name is not None:
        group.name = _normalize_required_text(name, field_name="name")
    if group_type is not None:
        if membership.role != "owner":
            raise ValueError("only owners can change shared group type")
        group.group_type = _normalize_choice(
            group_type,
            field_name="group_type",
            allowed=GROUP_TYPES,
        )
    if status is not None:
        if membership.role != "owner":
            raise ValueError("only owners can change shared group status")
        group.status = _normalize_choice(status, field_name="status", allowed=GROUP_STATUSES)

    group.updated_at = _utcnow()
    session.flush()
    group = _require_group(session, group_id=group.group_id)
    viewer_membership = _require_membership(session, group_id=group.group_id, user=actor)
    return _serialize_group(group, viewer_membership=viewer_membership, include_members=True)


def add_shared_group_member(
    session: Session,
    *,
    actor: User,
    group_id: str,
    user_id: str,
    role: str,
) -> dict[str, Any]:
    actor_membership = _require_manager(session, group_id=group_id, user=actor)
    target_user = session.get(User, user_id)
    if target_user is None or target_user.username == SERVICE_USERNAME:
        raise ValueError("user not found")
    normalized_role = _normalize_choice(role, field_name="role", allowed=MEMBER_ROLES)
    if actor_membership.role != "owner" and normalized_role == "owner":
        raise ValueError("only owners can assign owner role")

    existing = session.get(SharedGroupMember, {"group_id": group_id, "user_id": user_id})
    now = _utcnow()
    if existing is None:
        existing = SharedGroupMember(
            group_id=group_id,
            user_id=user_id,
            role=normalized_role,
            membership_status="active",
            joined_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(existing)
    else:
        existing.role = normalized_role
        existing.membership_status = "active"
        existing.updated_at = now
        if existing.joined_at is None:
            existing.joined_at = now
    session.flush()
    return get_shared_group_detail(session, user=actor, group_id=group_id)


def update_shared_group_member(
    session: Session,
    *,
    actor: User,
    group_id: str,
    user_id: str,
    role: str | None = None,
    membership_status: str | None = None,
) -> dict[str, Any]:
    actor_membership = _require_manager(session, group_id=group_id, user=actor)
    group = _require_group(session, group_id=group_id)
    target = session.get(SharedGroupMember, {"group_id": group_id, "user_id": user_id})
    if target is None:
        raise ValueError("shared group member not found")
    if actor_membership.role != "owner" and target.role == "owner":
        raise ValueError("only owners can update owner memberships")

    if role is not None:
        normalized_role = _normalize_choice(role, field_name="role", allowed=MEMBER_ROLES)
        if actor_membership.role != "owner" and normalized_role == "owner":
            raise ValueError("only owners can assign owner role")
        target.role = normalized_role
    if membership_status is not None:
        normalized_status = _normalize_choice(
            membership_status,
            field_name="membership_status",
            allowed=MEMBERSHIP_STATUSES,
        )
        if normalized_status != "active":
            return remove_shared_group_member(
                session,
                actor=actor,
                group_id=group.group_id,
                user_id=user_id,
            )
        target.membership_status = normalized_status

    owner_count = sum(
        1
        for member in group.memberships
        if member.membership_status == "active"
        and member.role == "owner"
        and not (member.user_id == user_id and target.role != "owner")
    )
    if owner_count == 0:
        raise ValueError("shared group must keep at least one active owner")

    target.updated_at = _utcnow()
    session.flush()
    return get_shared_group_detail(session, user=actor, group_id=group_id)


def remove_shared_group_member(
    session: Session,
    *,
    actor: User,
    group_id: str,
    user_id: str,
) -> dict[str, Any]:
    actor_membership = _require_manager(session, group_id=group_id, user=actor)
    group = _require_group(session, group_id=group_id)
    target = session.get(SharedGroupMember, {"group_id": group_id, "user_id": user_id})
    if target is None or target.membership_status != "active":
        raise ValueError("shared group member not found")
    if actor_membership.role != "owner" and target.role == "owner":
        raise ValueError("only owners can remove owner memberships")

    remaining_owner_count = sum(
        1
        for member in group.memberships
        if member.membership_status == "active"
        and member.role == "owner"
        and member.user_id != user_id
    )
    if target.role == "owner" and remaining_owner_count == 0:
        raise ValueError("shared group must keep at least one active owner")

    target.membership_status = "removed"
    target.updated_at = _utcnow()
    session.flush()
    return get_shared_group_detail(session, user=actor, group_id=group_id)
