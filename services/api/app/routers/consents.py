from fastapi import APIRouter, Depends, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..audit import append_audit_log
from ..database import get_db
from ..deps import get_current_user, require_membership
from ..errors import forbidden, not_found
from ..models import Consent, DataAccessAuditLog, User
from ..schemas import AuditLogOut, ConsentCreate, ConsentOut
from ..security import utc_now

router = APIRouter(tags=["consents"])


def is_consent_active(consent: Consent) -> bool:
    if consent.revoked_at is not None:
        return False
    if consent.expires_at is None:
        return True
    expires_at = consent.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=utc_now().tzinfo)
    return expires_at > utc_now()


def require_active_consent(
    db: Session,
    *,
    consent_id: str,
    subject_user_id: str,
    consent_type: str,
    grantee_user_id: str | None = None,
) -> Consent:
    consent = db.get(Consent, consent_id)
    if (
        consent is None
        or consent.subject_user_id != subject_user_id
        or consent.consent_type != consent_type
        or not is_consent_active(consent)
    ):
        from ..errors import consent_required

        raise consent_required()
    if (
        grantee_user_id is not None
        and consent.grantee_user_id is not None
        and consent.grantee_user_id != grantee_user_id
    ):
        from ..errors import consent_required

        raise consent_required()
    return consent


@router.get("/consents", response_model=list[ConsentOut])
def list_consents(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[Consent]:
    return list(
        db.scalars(
            select(Consent)
            .where(or_(Consent.subject_user_id == user.id, Consent.grantee_user_id == user.id))
            .order_by(Consent.granted_at.desc())
        ).all()
    )


@router.post("/consents", response_model=ConsentOut, status_code=201)
def create_consent(
    payload: ConsentCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Consent:
    if payload.subject_user_id != user.id:
        raise forbidden("只有信息主体本人可以授予此项授权")
    require_membership(db, payload.family_id, user.id)
    if payload.grantee_user_id:
        require_membership(db, payload.family_id, payload.grantee_user_id)
    consent = Consent(**payload.model_dump())
    db.add(consent)
    db.flush()
    append_audit_log(
        db,
        actor_id=user.id,
        action="consent.grant",
        resource_type="consent",
        resource_id=consent.id,
        reason=payload.consent_type,
        request=request,
    )
    db.commit()
    return consent


@router.get("/consents/{consent_id}", response_model=ConsentOut)
def get_consent(
    consent_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Consent:
    consent = db.get(Consent, consent_id)
    if consent is None or user.id not in {consent.subject_user_id, consent.grantee_user_id}:
        raise not_found("授权")
    return consent


@router.post("/consents/{consent_id}/revoke", response_model=ConsentOut)
def revoke_consent(
    consent_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Consent:
    consent = db.get(Consent, consent_id)
    if consent is None or consent.subject_user_id != user.id:
        raise not_found("授权")
    consent.revoked_at = utc_now()
    append_audit_log(
        db,
        actor_id=user.id,
        action="consent.revoke",
        resource_type="consent",
        resource_id=consent.id,
        reason=consent.consent_type,
        request=request,
    )
    db.commit()
    return consent


@router.get("/data-access-history", response_model=list[AuditLogOut])
def data_access_history(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[DataAccessAuditLog]:
    # The first version returns actions performed by the current user. Resource-owner
    # projections can be added once every auditable resource has an ownership map.
    return list(
        db.scalars(
            select(DataAccessAuditLog)
            .where(
                or_(
                    DataAccessAuditLog.actor_id == user.id,
                    (
                        (DataAccessAuditLog.resource_type == "user")
                        & (DataAccessAuditLog.resource_id == user.id)
                    ),
                )
            )
            .order_by(DataAccessAuditLog.created_at.desc())
            .limit(200)
        ).all()
    )
