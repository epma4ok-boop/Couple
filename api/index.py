from datetime import datetime, timedelta
from uuid import uuid4
import os

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.models import Challenge, ChallengeMember, Entry, User
from app.schemas import (
    ChallengeCreateIn,
    JoinInviteIn,
    ManualEntryIn,
    RematchIn,
    TelegramAuthIn,
)

# username бота по умолчанию — твой новый бот
BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "WeekUpChallenge_bot")

app = FastAPI(title="WeekUp API")
Base.metadata.create_all(bind=engine)


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _invite_code() -> str:
    return uuid4().hex[:8].upper()


def _user_or_404(db: Session, user_id: str) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _challenge_or_404(db: Session, challenge_id: str) -> Challenge:
    challenge = (
        db.query(Challenge).filter(Challenge.id == challenge_id).first()
    )
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")
    return challenge


def _member(db: Session, challenge_id: str, user_id: str):
    return (
        db.query(ChallengeMember)
        .filter(
            ChallengeMember.challenge_id == challenge_id,
            ChallengeMember.user_id == user_id,
        )
        .first()
    )


def _maybe_finalize(db: Session, challenge: Challenge) -> Challenge:
    if challenge.status == "completed":
        return challenge
    if challenge.end_at and datetime.utcnow() >= challenge.end_at:
        challenge.status = "completed"
        db.commit()
        db.refresh(challenge)
    return challenge


def _leaderboard(db: Session, challenge: Challenge):
    members = (
        db.query(ChallengeMember)
        .filter(
            ChallengeMember.challenge_id == challenge.id,
            ChallengeMember.status == "active",
        )
        .all()
    )
    today = datetime.utcnow().date()
    rows = []
    for m in members:
        user = db.query(User).filter(User.id == m.user_id).first()
        entries = (
            db.query(Entry)
            .filter(
                Entry.challenge_id == challenge.id,
                Entry.user_id == m.user_id,
            )
            .all()
        )
        total = sum(e.value for e in entries)
        today_sum = sum(e.value for e in entries if e.entry_date == today)
        rows.append(
            {
                "user_id": m.user_id,
                "display_name": user.display_name if user else m.user_id,
                "total": total,
                "today": today_sum,
            }
        )
    rows.sort(key=lambda r: (-r["total"], r["display_name"].lower()))
    for i, r in enumerate(rows, start=1):
        r["rank"] = i
    return rows


def _summary(db: Session, challenge: Challenge, user_id: str | None = None):
    challenge = _maybe_finalize(db, challenge)
    lb = _leaderboard(db, challenge)
    leader_total = lb[0]["total"] if lb else 0
    you = (
        next((r for r in lb if r["user_id"] == user_id), None)
        if user_id
        else None
    )
    gap = max(leader_total - (you["total"] if you else 0), 0)
    days_left = (
        max(
            (challenge.end_at.date() - datetime.utcnow().date()).days,
            0,
        )
        if challenge.end_at
        else 0
    )
    return {
        "status": challenge.status,
        "days_left": days_left,
        "your_rank": you["rank"] if you else None,
        "your_today": you["today"] if you else 0,
        "your_total": you["total"] if you else 0,
        "gap_to_leader": gap,
        "leader_total": leader_total,
        "leaderboard": lb,
    }


@app.get("/api")
def health_root():
    return {"ok": True}


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
            id=_uid("usr"),
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
def create_challenge(
    payload: ChallengeCreateIn, db: Session = Depends(get_db)
):
    _user_or_404(db, payload.creator_user_id)
    start = datetime.utcnow()
    end = start + timedelta(days=7)
    code = _invite_code()
    while db.query(Challenge).filter(Challenge.invite_code == code).first():
        code = _invite_code()

    challenge = Challenge(
        id=_uid("chl"),
        creator_user_id=payload.creator_user_id,
        title=payload.title,
        type=payload.type,
        mode=payload.mode,
        trust_mode=payload.trust_mode,
        duration_days=7,
        max_members=payload.max_members,
        status="active",
        invite_code=code,
        start_at=start,
        end_at=end,
    )
    db.add(challenge)
    db.flush()
    db.add(
        ChallengeMember(
            id=_uid("mem"),
            challenge_id=challenge.id,
            user_id=payload.creator_user_id,
            role="owner",
            status="active",
            sync_status="manual",
        )
    )
    db.commit()
    db.refresh(challenge)

    return {
        "challenge": {
            "id": challenge.id,
            "title": challenge.title,
            "type": challenge.type,
            "mode": challenge.mode,
            "trust_mode": challenge.trust_mode,
            "duration_days": 7,
            "max_members": challenge.max_members,
            "status": challenge.status,
            "invite_code": challenge.invite_code,
            "start_at": challenge.start_at.isoformat(),
            "end_at": challenge.end_at.isoformat(),
        },
        "invite_link": f"https://t.me/{BOT_USERNAME}?startapp={challenge.invite_code}",
    }


@app.get("/api/challenges/{challenge_id}")
def get_challenge(
    challenge_id: str,
    user_id: str | None = None,
    db: Session = Depends(get_db),
):
    ch = _challenge_or_404(db, challenge_id)
    summary = _summary(db, ch, user_id)
    return {
        "challenge": {
            "id": ch.id,
            "title": ch.title,
            "type": ch.type,
            "mode": ch.mode,
            "trust_mode": ch.trust_mode,
            "duration_days": 7,
            "max_members": ch.max_members,
            "status": ch.status,
            "invite_code": ch.invite_code,
            "start_at": ch.start_at.isoformat(),
            "end_at": ch.end_at.isoformat(),
        },
        "summary": summary,
        "leaderboard": summary["leaderboard"],
    }


@app.get("/api/invites/{code}")
def get_invite(code: str, db: Session = Depends(get_db)):
    ch = db.query(Challenge).filter(Challenge.invite_code == code).first()
    if not ch:
        raise HTTPException(status_code=404, detail="Invite not found")
    count = (
        db.query(ChallengeMember)
        .filter(
            ChallengeMember.challenge_id == ch.id,
            ChallengeMember.status == "active",
        )
        .count()
    )
    return {
        "invite_code": ch.invite_code,
        "challenge_id": ch.id,
        "title": ch.title,
        "mode": ch.mode,
        "type": ch.type,
        "status": ch.status,
        "member_count": count,
        "max_members": ch.max_members,
    }


@app.post("/api/invites/{code}/accept")
def accept_invite(
    code: str, payload: JoinInviteIn, db: Session = Depends(get_db)
):
    ch = db.query(Challenge).filter(Challenge.invite_code == code).first()
    if not ch:
        raise HTTPException(status_code=404, detail="Invite not found")
    _user_or_404(db, payload.user_id)
    existing = _member(db, ch.id, payload.user_id)
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
    m = ChallengeMember(
        id=_uid("mem"),
        challenge_id=ch.id,
        user_id=payload.user_id,
        role="member",
        status="active",
        sync_status="manual",
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return {
        "membership": {
            "id": m.id,
            "challenge_id": m.challenge_id,
            "user_id": m.user_id,
            "role": m.role,
            "status": m.status,
            "sync_status": m.sync_status,
        }
    }


@app.post("/api/challenges/{challenge_id}/entries/manual")
def add_manual_entry(
    challenge_id: str, payload: ManualEntryIn, db: Session = Depends(get_db)
):
    ch = _challenge_or_404(db, challenge_id)
    ch = _maybe_finalize(db, ch)
    if ch.status == "completed":
        raise HTTPException(
            status_code=400, detail="Challenge already completed"
        )
    m = _member(db, ch.id, payload.user_id)
    if not m:
        raise HTTPException(
            status_code=404, detail="Challenge member not found"
        )
    existing = (
        db.query(Entry)
        .filter(
            Entry.challenge_id == ch.id,
            Entry.user_id == payload.user_id,
            Entry.entry_date == payload.entry_date,
            Entry.source_type == "manual",
        )
        .first()
    )
    if existing:
        existing.value += payload.value
    else:
        db.add(
            Entry(
                id=_uid("ent"),
                challenge_id=ch.id,
                user_id=payload.user_id,
                entry_date=payload.entry_date,
                value=payload.value,
                source_type="manual",
                verified=False,
                raw_payload_hash=None,
            )
        )
    db.commit()
    summary = _summary(db, ch, payload.user_id)
    return {"status": "ok", "summary": summary, "leaderboard": summary["leaderboard"]}


@app.get("/api/challenges/{challenge_id}/leaderboard")
def get_leaderboard(
    challenge_id: str,
    user_id: str | None = None,
    db: Session = Depends(get_db),
):
    ch = _challenge_or_404(db, challenge_id)
    summary = _summary(db, ch, user_id)
    return {
        "challenge_id": ch.id,
        "summary": summary,
        "leaderboard": summary["leaderboard"],
    }


@app.post("/api/challenges/{challenge_id}/finalize")
def finalize_challenge(
    challenge_id: str, payload: RematchIn, db: Session = Depends(get_db)
):
    ch = _challenge_or_404(db, challenge_id)
    _user_or_404(db, payload.creator_user_id)
    ch.status = "completed"
    db.commit()
    summary = _summary(db, ch, payload.creator_user_id)
    winner = summary["leaderboard"][0] if summary["leaderboard"] else None
    return {
        "status": "completed",
        "challenge_id": ch.id,
        "winner": winner,
        "summary": summary,
    }
