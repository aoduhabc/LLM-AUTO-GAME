from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from game_store import InMemoryGameStore
from schemas import (
    DialogueChatRequest,
    DialogueChatResponse,
    DialogueHistoryResponse,
    EnterRegionRequest,
    EnterRegionResponse,
    KnownNpcResponse,
    NpcAutonomyStateResponse,
    NpcDetailResponse,
    PlayerProgressResponse,
    RegionConfig,
)


load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

store = InMemoryGameStore()
app = FastAPI(title="乡野絮语 API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/regions")
def list_regions() -> list[RegionConfig]:
    return list(store.regions.values())


@app.post("/api/region/enter", response_model=EnterRegionResponse)
def enter_region(payload: EnterRegionRequest) -> EnterRegionResponse:
    return store.enter_region(player_id=payload.player_id, region_id=payload.region_id)


@app.post("/api/dialogue/chat", response_model=DialogueChatResponse)
def dialogue_chat(payload: DialogueChatRequest) -> DialogueChatResponse:
    return store.chat(player_id=payload.player_id, npc_id=payload.npc_id, message=payload.message)


@app.get("/api/npc/{npc_id}", response_model=NpcDetailResponse)
def get_npc(npc_id: str) -> NpcDetailResponse:
    return store.get_npc(npc_id)


@app.get("/api/npc/{npc_id}/autonomy", response_model=NpcAutonomyStateResponse)
def get_npc_autonomy(npc_id: str) -> NpcAutonomyStateResponse:
    return store.get_npc_autonomy(npc_id=npc_id)


@app.get("/api/dialogue/history", response_model=DialogueHistoryResponse)
def get_dialogue_history(player_id: str, npc_id: str) -> DialogueHistoryResponse:
    return store.get_dialogue_history(player_id=player_id, npc_id=npc_id)


@app.get("/api/player/{player_id}/npcs", response_model=list[KnownNpcResponse])
def get_player_npcs(player_id: str) -> list[KnownNpcResponse]:
    return store.get_known_npcs(player_id=player_id)


@app.get("/api/player/{player_id}/progress", response_model=PlayerProgressResponse)
def get_player_progress(player_id: str) -> PlayerProgressResponse:
    return store.get_player_progress(player_id=player_id)
