from sqlmodel import SQLModel, Field
from sqlalchemy import Column, JSON, DateTime
from typing import Optional
from datetime import datetime

class WriterQueryLog(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    timestamp: datetime = Field(
        sa_column=Column(DateTime(timezone=True)),
        default_factory=datetime.utcnow
    )
    writer_id: str  # IBW, Razzball, Both, etc.
    feature: str  # summary, compare, trade
    context: Optional[str] = None
    summary_player: Optional[str] = None
    player_1: Optional[str] = None
    player_2: Optional[str] = None
    player_3: Optional[str] = None
    player_4: Optional[str] = None
    player_5: Optional[str] = None
    player_6: Optional[str] = None
    player_7: Optional[str] = None
    player_8: Optional[str] = None
    player_9: Optional[str] = None
    player_10: Optional[str] = None
    teamA_1: Optional[str] = None
    teamA_2: Optional[str] = None
    teamA_3: Optional[str] = None
    teamA_4: Optional[str] = None
    teamA_5: Optional[str] = None
    teamB_1: Optional[str] = None
    teamB_2: Optional[str] = None
    teamB_3: Optional[str] = None
    teamB_4: Optional[str] = None
    teamB_5: Optional[str] = None

class WriterProfile(SQLModel, table=True):
    writer_id: str = Field(primary_key=True)
    display_name: str
    email: str
    avatar_url: Optional[str] = None
    primary_website: Optional[str] = None
    socials: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    bot_config: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    last_updated: Optional[str] = None

class WriterUpload(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    writer_id: str
    filename: str
    file_type: str  # "avatar", "ranking", or "article"
    s3_path: str
    timestamp: datetime = Field(
        sa_column=Column(DateTime(timezone=True)),
        default_factory=datetime.utcnow
    )
