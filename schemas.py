from datetime import date
from typing import Literal, Optional
from pydantic import BaseModel, Field

class TelegramAuthIn(BaseModel):
    telegram_user_id: int
    username: Optional[str] = None
    display_name: str
    language: Literal['en', 'ru'] = 'en'
    timezone_name: str = 'UTC'

class ChallengeCreateIn(BaseModel):
    creator_user_id: str
    title: str = Field(min_length=3, max_length=80)
    type: Literal['steps', 'workout', 'daily_checkin'] = 'steps'
    mode: Literal['race', 'goal'] = 'race'
    trust_mode: Literal['manual', 'verified_sync', 'hybrid'] = 'manual'
    duration_days: int = Field(default=7, ge=1, le=30)
    max_members: int = Field(default=8, ge=2, le=50)

class JoinInviteIn(BaseModel):
    user_id: str

class ManualEntryIn(BaseModel):
    user_id: str
    entry_date: date
    value: int = Field(ge=0, le=100000)

class SyncConnectIn(BaseModel):
    user_id: str
    provider: Literal['healthkit', 'health_connect', 'pedometer']

class SyncImportIn(BaseModel):
    user_id: str
    provider: Literal['healthkit', 'health_connect', 'pedometer']
    entry_date: date
    value: int = Field(ge=0, le=100000)
    raw_payload_hash: str

class RematchIn(BaseModel):
    creator_user_id: str
