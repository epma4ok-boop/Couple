from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.models import Challenge, ChallengeMember, Entry, SyncSource, User
from app.schemas import (
    ChallengeCreateIn,
    JoinInviteIn,
    ManualEntryIn,
    RematchIn,
    SyncConnectIn,
    SyncImportIn,
    TelegramAuthIn,
)

app = FastAPI(title="WeekUp API")

Base.metadata.create_all(bind=engine)


def uid(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def invite_code() -> str:
    return uuid4().hex[:8].upper()


def get_user_or_404(db: Session, user_id: str) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def get_challenge_or_404(db: Session, challenge_id: str) -> Challenge:
    challenge = db.query(Challenge).filter(Challenge.id == challenge_id).first()
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")
    return challenge


def get_member(db: Session, challenge_id: str, user_id: str):
    return (
        db.query(ChallengeMember)
        .filter(
            ChallengeMember.challenge_id == challenge_id,
            ChallengeMember.user_id == user_id,
        )
        .first()
    )


def compute_leaderboard(db: Session, challenge: Challenge):
    members = (
        db.query(ChallengeMember)
        .filter(
            ChallengeMember.challenge_id == challenge.id,
            ChallengeMember.status == "active",
        )
        .all()
    )

    rows = []
    for member in members:
        user = db.query(User).filter(User.id == member.user_id).first()
        entries = (
            db.query(Entry)
            .filter(Entry.challenge_id == challenge.id, Entry.user_id == member.user_id)
            .all()
        )
        total = sum(item.value for item in entries)
        verified = any(item.verified for item in entries)
        rows.append(
            {
                "user_id": member.user_id,
                "display_name": user.display_name if user else member.user_id,
                "total": total,
                "verified": verified,
                "sync_status": member.sync_status,
            }
        )

    rows.sort(key=lambda x: (-x["total"], x["display_name"].lower()))
    for idx, row in enumerate(rows, start=1):
        row["rank"] = idx
    return rows


@app.get("/api")
def health():
    return {"status": "ok", "service": "weekup-api"}


@app.get("/api/ping")
def ping():
    return {"message": "pong"}


@app.post("/api/auth/telegram")
def auth_telegram(payload: TelegramAuthIn, db: Session = Depends(get_db)):
    user = (
        db.query(User)
        .filter(User.telegram_user_id == str(payload.telegram_user_id))
        .first()
    )

    if user:
        user.username = payload.username
        user.display_name = payload.display_name
        user.language = payload.language
        user.timezone_name = payload.timezone_name
    else:
        user = User(
            id=uid("usr"),
            telegram_user_id=str(payload.telegram_user_id),
            username=payload.username,
            display_name=payload.display_name,
            language=payload.language,
            timezone_name=payload.timezone_name,
        )
        db.add(user)

    db.commit()
    db.refresh(user)
    return {
        "user": {
            "id": user.id,
            "telegram_user_id": user.telegram_user_id,
            "username": user.username,
            "display_name": user.display_name,
            "language": user.language,
            "timezone_name": user.timezone_name,
        }
    }


@app.post("/api/challenges")
def create_challenge(payload: ChallengeCreateIn, db: Session = Depends(get_db)):
    get_user_or_404(db, payload.creator_user_id)

    start_at = datetime.utcnow()
    end_at = start_at + timedelta(days=payload.duration_days)

    code = invite_code()
    while db.query(Challenge).filter(Challenge.invite_code == code).first():
        code = invite_code()

    challenge = Challenge(
        id=uid("chl"),
        creator_user_id=payload.creator_user_id,
        title=payload.title,
        type=payload.type,
        mode=payload.mode,
        trust_mode=payload.trust_mode,
        duration_days=payload.duration_days,
        max_members=payload.max_members,
        status="active",
        invite_code=code,
        start_at=start_at,
        end_at=end_at,
    )
    db.add(challenge)
    db.flush()

    creator_member = ChallengeMember(
        id=uid("mem"),
        challenge_id=challenge.id,
        user_id=payload.creator_user_id,
        role="owner",
        status="active",
        sync_status="connected" if payload.trust_mode in {"verified_sync", "hybrid"} else "not_connected",
    )
    db.add(creator_member)
    db.commit()
    db.refresh(challenge)

    return {
        "challenge": {
            "id": challenge.id,
            "title": challenge.title,
            "type": challenge.type,
            "mode": challenge.mode,
            "trust_mode": challenge.trust_mode,
            "duration_days": challenge.duration_days,
            "max_members": challenge.max_members,
            "status": challenge.status,
            "invite_code": challenge.invite_code,
            "start_at": challenge.start_at.isoformat(),
            "end_at": challenge.end_at.isoformat(),
        },
        "invite_link": f"https://t.me/weekupbot?startapp={challenge.invite_code}",
    }


@app.get("/api/challenges/{challenge_id}")
def get_challenge(challenge_id: str, db: Session = Depends(get_db)):
    challenge = get_challenge_or_404(db, challenge_id)
    members = (
        db.query(ChallengeMember)
        .filter(ChallengeMember.challenge_id == challenge.id)
        .all()
    )
    leaderboard = compute_leaderboard(db, challenge)

    return {
        "challenge": {
            "id": challenge.id,
            "creator_user_id": challenge.creator_user_id,
            "title": challenge.title,
            "type": challenge.type,
            "mode": challenge.mode,
            "trust_mode": challenge.trust_mode,
            "duration_days": challenge.duration_days,
            "max_members": challenge.max_members,
            "status": challenge.status,
            "invite_code": challenge.invite_code,
            "start_at": challenge.start_at.isoformat(),
            "end_at": challenge.end_at.isoformat(),
            "members": [
                {
                    "user_id": m.user_id,
                    "role": m.role,
                    "status": m.status,
                    "sync_status": m.sync_status,
                }
                for m in members
            ],
        },
        "leaderboard": leaderboard,
    }


@app.get("/api/invites/{code}")
def get_invite(code: str, db: Session = Depends(get_db)):
    challenge = db.query(Challenge).filter(Challenge.invite_code == code).first()
    if not challenge:
        raise HTTPException(status_code=404, detail="Invite not found")

    member_count = (
        db.query(ChallengeMember)
        .filter(ChallengeMember.challenge_id == challenge.id, ChallengeMember.status == "active")
        .count()
    )

    return {
        "invite_code": challenge.invite_code,
        "challenge_id": challenge.id,
        "title": challenge.title,
        "trust_mode": challenge.trust_mode,
        "status": challenge.status,
        "member_count": member_count,
        "max_members": challenge.max_members,
    }


@app.post("/api/invites/{code}/accept")
def accept_invite(code: str, payload: JoinInviteIn, db: Session = Depends(get_db)):
    challenge = db.query(Challenge).filter(Challenge.invite_code == code).first()
    if not challenge:
        raise HTTPException(status_code=404, detail="Invite not found")

    get_user_or_404(db, payload.user_id)

    active_members_count = (
        db.query(ChallengeMember)
        .filter(ChallengeMember.challenge_id == challenge.id, ChallengeMember.status == "active")
        .count()
    )
    if active_members_count >= challenge.max_members:
        raise HTTPException(status_code=400, detail="Challenge is full")

    existing = get_member(db, challenge.id, payload.user_id)
    if existing:
        return {
            "membership": {
                "id": existing.id,
                "challenge_id": existing.challenge_id,
                "user_id": existing.user_id,
                "role": existing.role,
                "status": existing.status,
                "sync_status": existing.sync_status,
            }
        }

    sync_status = "connected" if challenge.trust_mode in {"verified_sync", "hybrid"} else "not_connected"
    member = ChallengeMember(
        id=uid("mem"),
        challenge_id=challenge.id,
        user_id=payload.user_id,
        role="member",
        status="active",
        sync_status=sync_status,
    )
    db.add(member)
    db.commit()
    db.refresh(member)

    return {
        "membership": {
            "id": member.id,
            "challenge_id": member.challenge_id,
            "user_id": member.user_id,
            "role": member.role,
            "status": member.status,
            "sync_status": member.sync_status,
        }
    }


@app.post("/api/challenges/{challenge_id}/entries/manual")
def add_manual_entry(challenge_id: str, payload: ManualEntryIn, db: Session = Depends(get_db)):
    challenge = get_challenge_or_404(db, challenge_id)
    member = get_member(db, challenge.id, payload.user_id)
    if not member:
        raise HTTPException(status_code=404, detail="Challenge member not found")

    existing = (
        db.query(Entry)
        .filter(
            Entry.challenge_id == challenge.id,
            Entry.user_id == payload.user_id,
            Entry.entry_date == payload.entry_date,
            Entry.source_type == "manual",
        )
        .first()
    )

    if existing:
        existing.value = payload.value
        existing.verified = False
    else:
        db.add(
            Entry(
                id=uid("ent"),
                challenge_id=challenge.id,
                user_id=payload.user_id,
                entry_date=payload.entry_date,
                value=payload.value,
                source_type="manual",
                verified=False,
                raw_payload_hash=None,
            )
        )

    db.commit()
    return {"status": "ok", "message": "Manual entry stored"}


@app.post("/api/sync/connect")
def connect_sync(payload: SyncConnectIn, db: Session = Depends(get_db)):
    get_user_or_404(db, payload.user_id)

    sync = db.query(SyncSource).filter(SyncSource.user_id == payload.user_id).first()
    if sync:
        sync.provider = payload.provider
        sync.status = "connected"
        sync.last_synced_at = datetime.utcnow()
    else:
        sync = SyncSource(
            id=uid("src"),
            user_id=payload.user_id,
            provider=payload.provider,
            status="connected",
            last_synced_at=datetime.utcnow(),
        )
        db.add(sync)

    db.query(ChallengeMember).filter(ChallengeMember.user_id == payload.user_id).update(
        {"sync_status": "connected"}
    )

    db.commit()
    db.refresh(sync)
    return {
        "sync_source": {
            "id": sync.id,
            "user_id": sync.user_id,
            "provider": sync.provider,
            "status": sync.status,
            "last_synced_at": sync.last_synced_at.isoformat() if sync.last_synced_at else None,
        }
    }


@app.post("/api/sync/import")
def import_sync(payload: SyncImportIn, db: Session = Depends(get_db)):
    get_user_or_404(db, payload.user_id)

    sync = db.query(SyncSource).filter(SyncSource.user_id == payload.user_id).first()
    if not sync:
        raise HTTPException(status_code=400, detail="Sync source not connected")

    memberships = (
        db.query(ChallengeMember)
        .join(Challenge, Challenge.id == ChallengeMember.challenge_id)
        .filter(ChallengeMember.user_id == payload.user_id, Challenge.status == "active")
        .all()
    )
    if not memberships:
        raise HTTPException(status_code=404, detail="No active challenge memberships found")

    created_entries = []
    for membership in memberships:
        existing = (
            db.query(Entry)
            .filter(
                Entry.challenge_id == membership.challenge_id,
                Entry.user_id == payload.user_id,
                Entry.entry_date == payload.entry_date,
                Entry.source_type == payload.provider,
            )
            .first()
        )
        if existing:
            existing.value = payload.value
            existing.verified = True
            existing.raw_payload_hash = payload.raw_payload_hash
            created_entries.append(existing.id)
        else:
            entry = Entry(
                id=uid("ent"),
                challenge_id=membership.challenge_id,
                user_id=payload.user_id,
                entry_date=payload.entry_date,
                value=payload.value,
                source_type=payload.provider,
                verified=True,
                raw_payload_hash=payload.raw_payload_hash,
            )
            db.add(entry)
            created_entries.append(entry.id)

        membership.sync_status = "connected"

    sync.last_synced_at = datetime.utcnow()
    db.commit()

    return {
        "status": "ok",
        "imported_entries": created_entries,
        "provider": payload.provider,
        "entry_date": payload.entry_date.isoformat(),
        "value": payload.value,
        "verified": True,
    }


@app.get("/api/challenges/{challenge_id}/leaderboard")
def get_leaderboard(challenge_id: str, db: Session = Depends(get_db)):
    challenge = get_challenge_or_404(db, challenge_id)
    return {"challenge_id": challenge.id, "leaderboard": compute_leaderboard(db, challenge)}


@app.post("/api/challenges/{challenge_id}/finalize")
def finalize_challenge(challenge_id: str, payload: RematchIn, db: Session = Depends(get_db)):
    challenge = get_challenge_or_404(db, challenge_id)
    get_user_or_404(db, payload.creator_user_id)

    leaderboard = compute_leaderboard(db, challenge)
    challenge.status = "completed"
    db.commit()

    winner = leaderboard[0] if leaderboard else None
    rematch_code = invite_code()

    return {
        "status": "completed",
        "challenge_id": challenge.id,
        "winner": winner,
        "rematch": {
            "creator_user_id": payload.creator_user_id,
            "suggested_invite_code": rematch_code,
        },
        "events": [
            "leaderboard_snapshot_persisted",
            "notifications_queued",
            "rematch_draft_prepared",
        ],
    }
