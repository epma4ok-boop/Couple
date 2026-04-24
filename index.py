from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.models import Challenge, ChallengeMember, Entry, User
from app.schemas import ChallengeCreateIn, JoinInviteIn, ManualEntryIn, RematchIn, TelegramAuthIn

app = FastAPI(title="WeekUp API")
Base.metadata.create_all(bind=engine)


def uid(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def invite_code() -> str:
    return uuid4().hex[:8].upper()


def get_user_or_404(db: Session, user_id: str):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def get_challenge_or_404(db: Session, challenge_id: str):
    challenge = db.query(Challenge).filter(Challenge.id == challenge_id).first()
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")
    return challenge


def get_member(db: Session, challenge_id: str, user_id: str):
    return db.query(ChallengeMember).filter(
        ChallengeMember.challenge_id == challenge_id,
        ChallengeMember.user_id == user_id,
    ).first()


def challenge_goal_target(challenge: Challenge):
    custom = getattr(challenge, 'goal_target', None)
    if custom:
        return custom
    if challenge.type == 'water':
        return 56
    if challenge.type == 'daily_checkin':
        return 28
    return 70000


def compute_leaderboard(db: Session, challenge: Challenge):
    members = db.query(ChallengeMember).filter(
        ChallengeMember.challenge_id == challenge.id,
        ChallengeMember.status == 'active'
    ).all()
    rows = []
    for member in members:
        user = db.query(User).filter(User.id == member.user_id).first()
        entries = db.query(Entry).filter(
            Entry.challenge_id == challenge.id,
            Entry.user_id == member.user_id
        ).all()
        total = sum(x.value for x in entries)
        today = 0
        today_key = datetime.utcnow().date()
        for x in entries:
            if x.entry_date == today_key:
                today += x.value
        rows.append({
            'user_id': member.user_id,
            'display_name': user.display_name if user else member.user_id,
            'total': total,
            'today': today,
            'verified': False,
            'sync_status': 'manual'
        })
    rows.sort(key=lambda x: (-x['total'], x['display_name'].lower()))
    for i, row in enumerate(rows, start=1):
        row['rank'] = i
    return rows


def challenge_summary(db: Session, challenge: Challenge, user_id: str | None = None):
    leaderboard = compute_leaderboard(db, challenge)
    target = challenge_goal_target(challenge)
    total_sum = sum(x['total'] for x in leaderboard)
    progress_percent = min(round((total_sum / target) * 100), 100) if target else 0
    you = next((x for x in leaderboard if x['user_id'] == user_id), None) if user_id else None
    leader_total = leaderboard[0]['total'] if leaderboard else 0
    your_gap = max(leader_total - (you['total'] if you else 0), 0)
    days_left = max((challenge.end_at.date() - datetime.utcnow().date()).days, 0) if challenge.end_at else 0
    member_count = len(leaderboard)
    return {
        'mode': challenge.mode,
        'type': challenge.type,
        'goal_target': target if challenge.mode == 'goal' else None,
        'goal_progress_total': total_sum if challenge.mode == 'goal' else None,
        'goal_progress_percent': progress_percent if challenge.mode == 'goal' else None,
        'days_left': days_left,
        'member_count': member_count,
        'your_rank': you['rank'] if you else None,
        'your_today': you['today'] if you else 0,
        'your_total': you['total'] if you else 0,
        'gap_to_leader': your_gap if challenge.mode == 'race' else None,
        'leader_total': leader_total,
        'leaderboard': leaderboard,
    }


@app.get('/api')
def health():
    return {'status': 'ok', 'service': 'weekup-api'}


@app.get('/api/ping')
def ping():
    return {'message': 'pong'}


@app.post('/api/auth/telegram')
def auth_telegram(payload: TelegramAuthIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.telegram_user_id == str(payload.telegram_user_id)).first()
    if user:
        user.username = payload.username
        user.display_name = payload.display_name
        user.language = payload.language
        user.timezone_name = payload.timezone_name
    else:
        user = User(
            id=uid('usr'),
            telegram_user_id=str(payload.telegram_user_id),
            username=payload.username,
            display_name=payload.display_name,
            language=payload.language,
            timezone_name=payload.timezone_name,
        )
        db.add(user)
    db.commit()
    db.refresh(user)
    return {'user': {
        'id': user.id,
        'telegram_user_id': user.telegram_user_id,
        'username': user.username,
        'display_name': user.display_name,
        'language': user.language,
        'timezone_name': user.timezone_name,
    }}


@app.post('/api/challenges')
def create_challenge(payload: ChallengeCreateIn, db: Session = Depends(get_db)):
    get_user_or_404(db, payload.creator_user_id)
    start_at = datetime.utcnow()
    end_at = start_at + timedelta(days=payload.duration_days)
    code = invite_code()
    while db.query(Challenge).filter(Challenge.invite_code == code).first():
        code = invite_code()

    challenge = Challenge(
        id=uid('chl'),
        creator_user_id=payload.creator_user_id,
        title=payload.title,
        type=payload.type,
        mode=payload.mode,
        trust_mode='manual',
        duration_days=payload.duration_days,
        max_members=payload.max_members,
        status='active',
        invite_code=code,
        start_at=start_at,
        end_at=end_at,
    )
    if hasattr(challenge, 'goal_target'):
        challenge.goal_target = payload.goal_target or challenge_goal_target(challenge)
    db.add(challenge)
    db.flush()
    db.add(ChallengeMember(
        id=uid('mem'),
        challenge_id=challenge.id,
        user_id=payload.creator_user_id,
        role='owner',
        status='active',
        sync_status='manual',
    ))
    db.commit()
    db.refresh(challenge)
    return {
        'challenge': {
            'id': challenge.id,
            'title': challenge.title,
            'type': challenge.type,
            'mode': challenge.mode,
            'trust_mode': challenge.trust_mode,
            'duration_days': challenge.duration_days,
            'max_members': challenge.max_members,
            'status': challenge.status,
            'invite_code': challenge.invite_code,
            'goal_target': challenge_goal_target(challenge) if challenge.mode == 'goal' else None,
            'start_at': challenge.start_at.isoformat(),
            'end_at': challenge.end_at.isoformat(),
        },
        'invite_link': f'https://t.me/weekupbot?startapp={challenge.invite_code}'
    }


@app.get('/api/challenges/{challenge_id}')
def get_challenge(challenge_id: str, user_id: str | None = None, db: Session = Depends(get_db)):
    challenge = get_challenge_or_404(db, challenge_id)
    summary = challenge_summary(db, challenge, user_id)
    return {
        'challenge': {
            'id': challenge.id,
            'creator_user_id': challenge.creator_user_id,
            'title': challenge.title,
            'type': challenge.type,
            'mode': challenge.mode,
            'trust_mode': challenge.trust_mode,
            'duration_days': challenge.duration_days,
            'max_members': challenge.max_members,
            'status': challenge.status,
            'invite_code': challenge.invite_code,
            'goal_target': challenge_goal_target(challenge) if challenge.mode == 'goal' else None,
            'start_at': challenge.start_at.isoformat(),
            'end_at': challenge.end_at.isoformat(),
        },
        'summary': summary,
        'leaderboard': summary['leaderboard']
    }


@app.get('/api/invites/{code}')
def get_invite(code: str, db: Session = Depends(get_db)):
    challenge = db.query(Challenge).filter(Challenge.invite_code == code).first()
    if not challenge:
        raise HTTPException(status_code=404, detail='Invite not found')
    members = db.query(ChallengeMember).filter(
        ChallengeMember.challenge_id == challenge.id,
        ChallengeMember.status == 'active'
    ).count()
    return {
        'invite_code': challenge.invite_code,
        'challenge_id': challenge.id,
        'title': challenge.title,
        'mode': challenge.mode,
        'type': challenge.type,
        'member_count': members,
        'max_members': challenge.max_members,
    }


@app.post('/api/invites/{code}/accept')
def accept_invite(code: str, payload: JoinInviteIn, db: Session = Depends(get_db)):
    challenge = db.query(Challenge).filter(Challenge.invite_code == code).first()
    if not challenge:
        raise HTTPException(status_code=404, detail='Invite not found')
    get_user_or_404(db, payload.user_id)
    existing = get_member(db, challenge.id, payload.user_id)
    if existing:
        return {'membership': {
            'id': existing.id,
            'challenge_id': existing.challenge_id,
            'user_id': existing.user_id,
            'role': existing.role,
            'status': existing.status,
            'sync_status': existing.sync_status,
        }}
    member = ChallengeMember(
        id=uid('mem'),
        challenge_id=challenge.id,
        user_id=payload.user_id,
        role='member',
        status='active',
        sync_status='manual',
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return {'membership': {
        'id': member.id,
        'challenge_id': member.challenge_id,
        'user_id': member.user_id,
        'role': member.role,
        'status': member.status,
        'sync_status': member.sync_status,
    }}


@app.post('/api/challenges/{challenge_id}/entries/manual')
def add_manual_entry(challenge_id: str, payload: ManualEntryIn, db: Session = Depends(get_db)):
    challenge = get_challenge_or_404(db, challenge_id)
    member = get_member(db, challenge.id, payload.user_id)
    if not member:
        raise HTTPException(status_code=404, detail='Challenge member not found')
    existing = db.query(Entry).filter(
        Entry.challenge_id == challenge.id,
        Entry.user_id == payload.user_id,
        Entry.entry_date == payload.entry_date,
        Entry.source_type == 'manual',
    ).first()
    if existing:
        existing.value = payload.value
        existing.verified = False
    else:
        db.add(Entry(
            id=uid('ent'),
            challenge_id=challenge.id,
            user_id=payload.user_id,
            entry_date=payload.entry_date,
            value=payload.value,
            source_type='manual',
            verified=False,
            raw_payload_hash=None,
        ))
    db.commit()
    summary = challenge_summary(db, challenge, payload.user_id)
    return {
        'status': 'ok',
        'message': 'Manual entry stored',
        'summary': summary,
        'leaderboard': summary['leaderboard']
    }


@app.get('/api/challenges/{challenge_id}/leaderboard')
def get_leaderboard(challenge_id: str, user_id: str | None = None, db: Session = Depends(get_db)):
    challenge = get_challenge_or_404(db, challenge_id)
    summary = challenge_summary(db, challenge, user_id)
    return {
        'challenge_id': challenge.id,
        'mode': challenge.mode,
        'summary': summary,
        'leaderboard': summary['leaderboard']
    }


@app.post('/api/challenges/{challenge_id}/finalize')
def finalize_challenge(challenge_id: str, payload: RematchIn, db: Session = Depends(get_db)):
    challenge = get_challenge_or_404(db, challenge_id)
    get_user_or_404(db, payload.creator_user_id)
    summary = challenge_summary(db, challenge, payload.creator_user_id)
    challenge.status = 'completed'
    db.commit()
    winner = summary['leaderboard'][0] if summary['leaderboard'] else None
    return {
        'status': 'completed',
        'challenge_id': challenge.id,
        'winner': winner,
        'summary': summary,
        'events': [
            'leaderboard_snapshot_persisted',
            'notifications_queued',
            'rematch_draft_prepared',
        ],
    }
