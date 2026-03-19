export type Position = {
  x: number;
  y: number;
};

export type Region = {
  region_id: string;
  region_name: string;
  region_type: string;
  spawn_points: Position[];
  theme_tags: string[];
};

export type RegionEnterNpc = {
  npc_id: string;
  name: string;
  role: string;
  position: Position;
  opening_line: string;
};

export type EnterRegionResponse = {
  first_visit: boolean;
  npc_generated: boolean;
  npcs: RegionEnterNpc[];
  event_text: string;
  story_fragment: string;
  is_new_fragment: boolean;
};

export type ChatResponse = {
  reply_text: string;
  emotion: string;
  suggestions: string[];
};

export type NpcProfile = {
  npc_id: string;
  name: string;
  role: string;
  personality: string[];
  mood: string;
  background: string;
  memory_summary: string;
  region_id: string;
  last_interaction_at: string | null;
};

export type ChatMessage = {
  id: string;
  speaker: "player" | "npc";
  content: string;
};

export type DialogueHistoryResponse = {
  player_id: string;
  npc_id: string;
  history: {
    speaker: "player" | "npc";
    content: string;
  }[];
};

export type KnownNpc = {
  npc_id: string;
  name: string;
  role: string;
  region_id: string;
  memory_summary: string;
  relationship: "陌生" | "点头之交" | "熟悉" | "信任";
  chat_count: number;
  last_interaction_at: string | null;
};

export type PlayerEventItem = {
  created_at: string;
  text: string;
  region_id: string;
};

export type PlayerProgress = {
  player_id: string;
  explored_region_ids: string[];
  story_fragments: string[];
  recent_events: PlayerEventItem[];
};
