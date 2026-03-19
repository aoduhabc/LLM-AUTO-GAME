import { create } from "zustand";
import type { ChatMessage, NpcProfile, Region, RegionEnterNpc } from "./types";

type GameState = {
  playerId: string;
  regions: Region[];
  playerPosition: { x: number; y: number };
  currentRegionId: string | null;
  exploredRegions: string[];
  npcs: RegionEnterNpc[];
  activeNpc: RegionEnterNpc | null;
  activeNpcProfile: NpcProfile | null;
  messages: ChatMessage[];
  suggestions: string[];
  setRegions: (regions: Region[]) => void;
  movePlayer: (x: number, y: number) => void;
  setCurrentRegion: (regionId: string | null) => void;
  addExploredRegion: (regionId: string) => void;
  upsertNpcs: (npcs: RegionEnterNpc[]) => void;
  setActiveNpc: (npc: RegionEnterNpc | null) => void;
  setActiveNpcProfile: (profile: NpcProfile | null) => void;
  appendMessage: (message: ChatMessage) => void;
  setSuggestions: (suggestions: string[]) => void;
  clearMessages: () => void;
};

export const useGameStore = create<GameState>((set) => ({
  playerId: "player_001",
  regions: [],
  playerPosition: { x: 1, y: 1 },
  currentRegionId: null,
  exploredRegions: [],
  npcs: [],
  activeNpc: null,
  activeNpcProfile: null,
  messages: [],
  suggestions: [],
  setRegions: (regions) => set({ regions }),
  movePlayer: (x, y) => set({ playerPosition: { x, y } }),
  setCurrentRegion: (regionId) => set({ currentRegionId: regionId }),
  addExploredRegion: (regionId) =>
    set((state) => ({
      exploredRegions: state.exploredRegions.includes(regionId)
        ? state.exploredRegions
        : [...state.exploredRegions, regionId]
    })),
  upsertNpcs: (npcs) =>
    set((state) => {
      const npcMap = new Map(state.npcs.map((npc) => [npc.npc_id, npc]));
      npcs.forEach((npc) => npcMap.set(npc.npc_id, npc));
      return { npcs: Array.from(npcMap.values()) };
    }),
  setActiveNpc: (npc) => set({ activeNpc: npc }),
  setActiveNpcProfile: (profile) => set({ activeNpcProfile: profile }),
  appendMessage: (message) => set((state) => ({ messages: [...state.messages, message] })),
  setSuggestions: (suggestions) => set({ suggestions }),
  clearMessages: () => set({ messages: [] })
}));
