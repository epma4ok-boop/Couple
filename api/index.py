from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.models import Challenge, ChallengeMember, Entry, SyncSource, User
from app.schemas import ChallengeCreateIn, JoinInviteIn, ManualEntryIn, RematchIn, SyncConnectIn, SyncImportIn, TelegramAuthIn

Base.metadata.create_all(bind=engine)

app = FastAPI(title='WeekUp API', version='0.2.0')
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


def make_id(prefix: str) -> str:
    return f'{prefix}_{uuid4().hex[:10]}'


def invite_code() -> str:
    return uuid4().hex[:7].upper()


def now_utc():
    return datetime.now(timezone.utc)


def ensure_user(db: Session, user_id: str) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail='user_not_found')
    return user


def ensure_challenge(db: Session, challenge_id: str) -> Challenge:
    challenge = db.query(Challenge).filter(Challenge.id == challenge_id).first()
    if not challenge:
        raise HTTPException(status_code=404, detail='challenge_not_found')
    return challenge


def leaderboard_for(db: Session, challenge_id: str):
    challenge = ensure_challenge(db, challenge_id)
    members = db.query(ChallengeMember).filter(ChallengeMember.challenge_id == challenge_id, ChallengeMember.status == 'active').all()
    totals = {m.user_id: 0 for m in members}
    entries = db.query(Entry).filter(Entry.challenge_id == challenge_id).all()
    for entry in entries:
        if challenge.trust_mode == 'manual' and entry.source_type != 'manual':
            continue
        if challenge.trust_mode == 'verified_sync' and not entry.verified:
            continue
        totals[entry.user_id] = totals.get(entry.user_id, 0) + entry.value
    rows = []
    for user_id, total in totals.items():
        user = db.query(User).filter(User.id == user_id).first()
        rows.append({
            'user_id': user_id,
            'display_name': user.display_name if user else user_id,
            'total': total,
            'verified_room': challenge.trust_mode == 'verified_sync'
        })
    rows.sort(key=lambda x: x['total'], reverse=True)
    for idx, row in enumerate(rows, start=1):
        row['rank'] = idx
    return rows


@app.get('/api')
def root():
    return {'service': 'weekup-api', 'status': 'ok', 'time': now_utc().isoformat()}


@app.post('/api/auth/telegram')
def auth_telegram(payload: TelegramAuthIn, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.telegram_user_id == str(payload.telegram_user_id)).first()
    if existing:
        existing.username = payload.username
        existing.display_name = payload.display_name
        existing.language = payload.language
        existing.timezone_name = payload.timezone_name
        db.commit()
        db.refresh(existing)
        return {'user': {
            'id': existing.id,
            'telegram_user_id': existing.telegram_user_id,
            'username': existing.username,
            'display_name': existing.display_name,
            'language': existing.language,
            'timezone_name': existing.timezone_name,
        }}
    user = User(
        id=make_id('usr'),
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


@app.get('/api/me/{user_id}')
def get_me(user_id: str, db: Session = Depends(get_db)):
    user = ensure_user(db, user_id)
    return {'user': {'id': user.id, 'display_name': user.display_name, 'language': user.language}}


@app.post('/api/challenges')
def create_challenge(payload: ChallengeCreateIn, db: Session = Depends(get_db)):
    creator = ensure_user(db, payload.creator_user_id)
    challenge = Challenge(
        id=make_id('chl'),
        creator_user_id=creator.id,
        title=payload.title,
        type=payload.type,
        mode=payload.mode,
        trust_mode=payload.trust_mode,
        duration_days=payload.duration_days,
        max_members=payload.max_members,
        status='pending_start',
        invite_code=invite_code(),
        start_at=now_utc(),
        end_at=now_utc() + timedelta(days=payload.duration_days),
    )
    db.add(challenge)
    db.flush()
    member = ChallengeMember(
        id=make_id('mem'),
        challenge_id=challenge.id,
        user_id=creator.id,
        role='creator',
        status='active',
        sync_status='not_connected'
    )
    db.add(member)
    db.commit()
    db.refresh(challenge)
    return {'challenge': {
        'id': challenge.id,
        'title': challenge.title,
        'type': challenge.type,
        'mode': challenge.mode,
        'trust_mode': challenge.trust_mode,
        'status': challenge.status,
        'invite_code': challenge.invite_code,
    }, 'invite_link': f'https://t.me/weekupbot?startapp={challenge.invite_code}'}


@app.get('/api/challenges/{challenge_id}')
def get_challenge(challenge_id: str, db: Session = Depends(get_db)):
    challenge = ensure_challenge(db, challenge_id)
    members = db.query(ChallengeMember).filter(ChallengeMember.challenge_id == challenge.id).all()
    return {'challenge': {
        'id': challenge.id,
        'title': challenge.title,
        'type': challenge.type,
        'mode': challenge.mode,
        'trust_mode': challenge.trust_mode,
        'status': challenge.status,
        'members': [{'user_id': m.user_id, 'role': m.role, 'status': m.status, 'sync_status': m.sync_status} for m in members]
    }, 'leaderboard': leaderboard_for(db, challenge_id)}


@app.get('/api/invites/{code}')
def get_invite_preview(code: str, db: Session = Depends(get_db)):
    challenge = db.query(Challenge).filter(Challenge.invite_code == code).first()
    if not challenge:
        raise HTTPException(status_code=404, detail='invite_not_found')
    member_count = db.query(func.count(ChallengeMember.id)).filter(ChallengeMember.challenge_id == challenge.id).scalar()
    return {'invite_code': code, 'challenge_id': challenge.id, 'title': challenge.title, 'trust_mode': challenge.trust_mode, 'member_count': member_count, 'status': challenge.status}


@app.post('/api/invites/{code}/accept')
def accept_invite(code: str, payload: JoinInviteIn, db: Session = Depends(get_db)):
    challenge = db.query(Challenge).filter(Challenge.invite_code == code).first()
    if not challenge:
        raise HTTPException(status_code=404, detail='invite_not_found')
    ensure_user(db, payload.user_id)
    existing = db.query(ChallengeMember).filter(ChallengeMember.challenge_id == challenge.id, ChallengeMember.user_id == payload.user_id).first()
    if existing:
        return {'joined': True, 'already_member': True, 'challenge_id': challenge.id}
    count = db.query(func.count(ChallengeMember.id)).filter(ChallengeMember.challenge_id == challenge.id).scalar()
    if count >= challenge.max_members:
        raise HTTPException(status_code=400, detail='challenge_full')
    member = ChallengeMember(id=make_id('mem'), challenge_id=challenge.id, user_id=payload.user_id, role='member', status='active', sync_status='not_connected')
    db.add(member)
    db.commit()
    return {'joined': True, 'already_member': False, 'challenge_id': challenge.id}


@app.post('/api/challenges/{challenge_id}/entries/manual')
def add_manual_entry(challenge_id: str, payload: ManualEntryIn, db: Session = Depends(get_db)):
    challenge = ensure_challenge(db, challenge_id)
    ensure_user(db, payload.user_id)
    if challenge.trust_mode == 'verified_sync':
        raise HTTPException(status_code=400, detail='manual_entries_not_allowed')
    if payload.value > 50000:
        raise HTTPException(status_code=400, detail='manual_value_flagged_too_high')
    entry = Entry(id=make_id('ent'), challenge_id=challenge_id, user_id=payload.user_id, entry_date=payload.entry_date, value=payload.value, source_type='manual', verified=False)
    db.add(entry)
    db.commit()
    return {'accepted': True, 'leaderboard': leaderboard_for(db, challenge_id)}


@app.post('/api/sync/connect')
def connect_sync_source(payload: SyncConnectIn, db: Session = Depends(get_db)):
    ensure_user(db, payload.user_id)
    source = db.query(SyncSource).filter(SyncSource.user_id == payload.user_id).first()
    if source:
        source.provider = payload.provider
        source.status = 'connected'
    else:
        source = SyncSource(id=make_id('src'), user_id=payload.user_id, provider=payload.provider, status='connected')
        db.add(source)
    members = db.query(ChallengeMember).filter(ChallengeMember.user_id == payload.user_id).all()
    for member in members:
        member.sync_status = 'connected'
    db.commit()
    return {'sync_source': {'user_id': source.user_id, 'provider': source.provider, 'status': source.status}}


@app.post('/api/sync/import')
def import_sync(payload: SyncImportIn, db: Session = Depends(get_db)):
    ensure_user(db, payload.user_id)
    source = db.query(SyncSource).filter(SyncSource.user_id == payload.user_id, SyncSource.provider == payload.provider).first()
    if not source:
        raise HTTPException(status_code=400, detail='sync_source_not_connected')
    source.last_synced_at = now_utc()
    memberships = db.query(ChallengeMember).filter(ChallengeMember.user_id == payload.user_id, ChallengeMember.status == 'active').all()
    created = []
    for membership in memberships:
        challenge = ensure_challenge(db, membership.challenge_id)
        if challenge.trust_mode not in ('verified_sync', 'hybrid'):
            continue
        entry = Entry(id=make_id('ent'), challenge_id=challenge.id, user_id=payload.user_id, entry_date=payload.entry_date, value=payload.value, source_type='health_sync', verified=True, raw_payload_hash=payload.raw_payload_hash)
        db.add(entry)
        created.append({'challenge_id': challenge.id, 'value': payload.value, 'verified': True})
    db.commit()
    return {'imported': len(created), 'entries': created}


@app.get('/api/sync/status/{user_id}')
def sync_status(user_id: str, db: Session = Depends(get_db)):
    ensure_user(db, user_id)
    source = db.query(SyncSource).filter(SyncSource.user_id == user_id).first()
    if not source:
        return {'sync_source': None}
    return {'sync_source': {'user_id': source.user_id, 'provider': source.provider, 'status': source.status}}


@app.get('/api/challenges/{challenge_id}/leaderboard')
def get_leaderboard(challenge_id: str, db: Session = Depends(get_db)):
    return {'items': leaderboard_for(db, challenge_id)}


@app.post('/api/challenges/{challenge_id}/rematch')
def create_rematch(challenge_id: str, payload: RematchIn, db: Session = Depends(get_db)):
    challenge = ensure_challenge(db, challenge_id)
    ensure_user(db, payload.creator_user_id)
    clone = ChallengeCreateIn(
        creator_user_id=payload.creator_user_id,
        title=f'{challenge.title} Rematch',
        type=challenge.type,
        mode=challenge.mode,
        trust_mode=challenge.trust_mode,
        duration_days=challenge.duration_days,
        max_members=challenge.max_members,
    )
    return create_challenge(clone, db)


@app.post('/api/challenges/{challenge_id}/finalize')
def finalize_challenge(challenge_id: str, db: Session = Depends(get_db)):
    challenge = ensure_challenge(db, challenge_id)
    challenge.status = 'completed'
    db.commit()
    rows = leaderboard_for(db, challenge_id)
    return {'challenge_id': challenge_id, 'status': 'completed', 'winner': rows[0] if rows else None, 'leaderboard': rows}
