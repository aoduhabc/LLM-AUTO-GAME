from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Position(BaseModel):
    x: int
    y: int


class RegionConfig(BaseModel):
    region_id: str
    region_name: str
    region_type: str
    spawn_points: list[Position]
    theme_tags: list[str]


class NpcProfile(BaseModel):
    npc_id: str
    region_id: str
    name: str
    role: str
    personality: list[str]
    mood: str
    location: str
    background: str
    opening_line: str
    memory_summary: str = ""
    last_interaction_at: datetime | None = None
    position: Position


class EnterRegionRequest(BaseModel):
    player_id: str = Field(min_length=1)
    region_id: str = Field(min_length=1)


class EnterRegionResponseNpc(BaseModel):
    npc_id: str
    name: str
    role: str
    position: Position
    opening_line: str


class EnterRegionResponse(BaseModel):
    first_visit: bool
    npc_generated: bool
    npcs: list[EnterRegionResponseNpc]
    event_text: str
    story_fragment: str
    is_new_fragment: bool
    rumor_text: str
    is_new_rumor: bool


class DialogueChatRequest(BaseModel):
    player_id: str = Field(min_length=1)
    npc_id: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=200)


class DialogueChatResponse(BaseModel):
    reply_text: str
    emotion: str
    suggestions: list[str]


class NpcDetailResponse(BaseModel):
    npc_id: str
    name: str
    role: str
    personality: list[str]
    mood: str
    background: str
    memory_summary: str
    region_id: str
    last_interaction_at: datetime | None


class DialogueHistoryItem(BaseModel):
    speaker: Literal["player", "npc"]
    content: str


class DialogueHistoryResponse(BaseModel):
    player_id: str
    npc_id: str
    history: list[DialogueHistoryItem]


class KnownNpcResponse(BaseModel):
    npc_id: str
    name: str
    role: str
    region_id: str
    memory_summary: str
    relationship: Literal["陌生", "点头之交", "熟悉", "信任"]
    chat_count: int
    last_interaction_at: datetime | None


class PlayerEventItem(BaseModel):
    created_at: datetime
    text: str
    region_id: str


class PlayerProgressResponse(BaseModel):
    player_id: str
    explored_region_ids: list[str]
    story_fragments: list[str]
    rumors: list[str]
    recent_events: list[PlayerEventItem]


class NpcAutonomyActionItem(BaseModel):
    created_at: datetime
    tick: int
    action_type: Literal["idle", "move", "share_rumor", "create_event"]
    action_text: str
    region_id: str


class NpcAutonomyStateResponse(BaseModel):
    npc_id: str
    world_tick: int
    day_phase: Literal["清晨", "白昼", "黄昏", "夜晚"]
    autonomy_memory: str
    session_logs: list[str]
    recent_actions: list[NpcAutonomyActionItem]
