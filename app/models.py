from datetime import datetime
from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from .database import Base

class User(Base):
    __tablename__ = 'users'
    id = Column(String, primary_key=True, index=True)
    telegram_user_id = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, nullable=True)
    display_name = Column(String, nullable=False)
    language = Column(String, nullable=False, default='en')
    timezone_name = Column(String, nullable=False, default='UTC')
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class Challenge(Base):
    __tablename__ = 'challenges'
    id = Column(String, primary_key=True, index=True)
    creator_user_id = Column(String, ForeignKey('users.id'), nullable=False)
    title = Column(String, nullable=False)
    type = Column(String, nullable=False)
    mode = Column(String, nullable=False)
    trust_mode = Column(String, nullable=False)
    duration_days = Column(Integer, nullable=False, default=7)
    max_members = Column(Integer, nullable=False, default=8)
    status = Column(String, nullable=False, default='pending_start')
    invite_code = Column(String, unique=True, index=True, nullable=False)
    start_at = Column(DateTime, nullable=False)
    end_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class ChallengeMember(Base):
    __tablename__ = 'challenge_members'
    id = Column(String, primary_key=True, index=True)
    challenge_id = Column(String, ForeignKey('challenges.id'), nullable=False, index=True)
    user_id = Column(String, ForeignKey('users.id'), nullable=False, index=True)
    role = Column(String, nullable=False, default='member')
    status = Column(String, nullable=False, default='active')
    sync_status = Column(String, nullable=False, default='not_connected')
    joined_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class Entry(Base):
    __tablename__ = 'entries'
    id = Column(String, primary_key=True, index=True)
    challenge_id = Column(String, ForeignKey('challenges.id'), nullable=False, index=True)
    user_id = Column(String, ForeignKey('users.id'), nullable=False, index=True)
    entry_date = Column(Date, nullable=False)
    value = Column(Integer, nullable=False)
    source_type = Column(String, nullable=False)
    verified = Column(Boolean, nullable=False, default=False)
    raw_payload_hash = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class SyncSource(Base):
    __tablename__ = 'sync_sources'
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey('users.id'), nullable=False, unique=True, index=True)
    provider = Column(String, nullable=False)
    status = Column(String, nullable=False, default='connected')
    last_synced_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
