import type {
  ChatResponse,
  DialogueHistoryResponse,
  EnterRegionResponse,
  KnownNpc,
  PlayerProgress,
  NpcProfile,
  Region
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8001/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json"
    },
    ...init
  });
  if (!response.ok) {
    throw new Error(`请求失败: ${response.status}`);
  }
  return (await response.json()) as T;
}

export function fetchRegions() {
  return request<Region[]>("/regions");
}

export function enterRegion(playerId: string, regionId: string) {
  return request<EnterRegionResponse>("/region/enter", {
    method: "POST",
    body: JSON.stringify({
      player_id: playerId,
      region_id: regionId
    })
  });
}

export function chatWithNpc(playerId: string, npcId: string, message: string) {
  return request<ChatResponse>("/dialogue/chat", {
    method: "POST",
    body: JSON.stringify({
      player_id: playerId,
      npc_id: npcId,
      message
    })
  });
}

export function getNpcProfile(npcId: string) {
  return request<NpcProfile>(`/npc/${npcId}`);
}

export function getDialogueHistory(playerId: string, npcId: string) {
  const query = new URLSearchParams({
    player_id: playerId,
    npc_id: npcId
  }).toString();
  return request<DialogueHistoryResponse>(`/dialogue/history?${query}`);
}

export function getKnownNpcs(playerId: string) {
  return request<KnownNpc[]>(`/player/${playerId}/npcs`);
}

export function getPlayerProgress(playerId: string) {
  return request<PlayerProgress>(`/player/${playerId}/progress`);
}
