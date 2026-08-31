import asyncio
from datetime import timedelta

from sqlalchemy import select

from .database import SessionLocal
from .models import CareReport, Consent, User
from .routers.care import generate_report
from .routers.consents import is_consent_active
from .schemas import ReportGenerate
from .security import utc_now


def generate_due_care_reports() -> int:
    db = SessionLocal()
    generated = 0
    try:
        grants = db.scalars(
            select(Consent).where(
                Consent.consent_type == "conversation_summary",
                Consent.revoked_at.is_(None),
            )
        ).all()
        elder_ids = {grant.subject_user_id for grant in grants if is_consent_active(grant)}
        for elder_id in elder_ids:
            recent = db.scalar(
                select(CareReport.id)
                .where(
                    CareReport.elder_user_id == elder_id,
                    CareReport.created_at >= utc_now() - timedelta(days=6),
                )
                .limit(1)
            )
            elder = db.get(User, elder_id)
            if recent is not None or elder is None or elder.status != "active":
                continue
            generate_report(elder_id, ReportGenerate(period_days=7), user=elder, db=db)
            generated += 1
        return generated
    except Exception:
        db.rollback()
        return generated
    finally:
        db.close()


async def care_report_scheduler(interval_seconds: int) -> None:
    while True:
        await asyncio.to_thread(generate_due_care_reports)
        await asyncio.sleep(max(300, interval_seconds))
