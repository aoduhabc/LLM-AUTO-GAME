import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  chatWithNpc,
  enterRegion,
  fetchRegions,
  getDialogueHistory,
  getKnownNpcs,
  getNpcAutonomy,
  getNpcProfile,
  getPlayerProgress
} from "./api";
import { useGameStore } from "./store";
import type { KnownNpc, NpcAutonomyState, PlayerEventItem, RegionEnterNpc } from "./types";

const GRID_WIDTH = 16;
const GRID_HEIGHT = 12;
const CELL_SIZE = 44;

type RegionZone = {
  regionId: string;
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
};

const regionZones: RegionZone[] = [
  { regionId: "region_road_01", minX: 0, maxX: 4, minY: 0, maxY: 3 },
  { regionId: "region_wheat_01", minX: 5, maxX: 9, minY: 0, maxY: 4 },
  { regionId: "region_bridge_01", minX: 10, maxX: 15, minY: 4, maxY: 7 },
  { regionId: "region_orchard_01", minX: 0, maxX: 6, minY: 8, maxY: 11 },
  { regionId: "region_market_01", minX: 7, maxX: 12, minY: 8, maxY: 11 },
  { regionId: "region_teahouse_01", minX: 11, maxX: 15, minY: 0, maxY: 3 }
];

function findRegionId(x: number, y: number): string | null {
  const zone = regionZones.find((z) => x >= z.minX && x <= z.maxX && y >= z.minY && y <= z.maxY);
  return zone?.regionId ?? null;
}

function distance(ax: number, ay: number, bx: number, by: number) {
  return Math.abs(ax - bx) + Math.abs(ay - by);
}

function formatTimeLabel(value: string | null) {
  if (!value) {
    return "暂无记录";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "暂无记录";
  }
  return date.toLocaleString("zh-CN", {
    hour12: false
  });
}

type AvatarProfile = {
  emoji: string;
  tintClass: string;
};

function buildAvatarSeed(text: string) {
  return Array.from(text).reduce((sum, char) => sum + char.charCodeAt(0), 0);
}

function getPlayerAvatar(playerId: string): AvatarProfile {
  const emojis = ["🧑", "🧒", "🧭", "👜", "👣"];
  const tints = ["avatar-amber", "avatar-orange", "avatar-coral"];
  const seed = buildAvatarSeed(playerId);
  return {
    emoji: emojis[seed % emojis.length],
    tintClass: tints[seed % tints.length]
  };
}

function getNpcAvatar(name: string, role: string): AvatarProfile {
  const emojis = ["👩‍🌾", "🧓", "🧑‍🍳", "🧑‍🔧", "👨‍🌾", "👩‍🦱", "👨‍🦳", "🧑‍🌾"];
  const tints = ["avatar-mint", "avatar-olive", "avatar-teal", "avatar-sage"];
  const seed = buildAvatarSeed(`${name}-${role}`);
  return {
    emoji: emojis[seed % emojis.length],
    tintClass: tints[seed % tints.length]
  };
}

export default function App() {
  const {
    playerId,
    regions,
    playerPosition,
    currentRegionId,
    npcs,
    activeNpc,
    activeNpcProfile,
    exploredRegions,
    messages,
    suggestions,
    setRegions,
    movePlayer,
    setCurrentRegion,
    addExploredRegion,
    upsertNpcs,
    setActiveNpc,
    setActiveNpcProfile,
    appendMessage,
    setSuggestions,
    clearMessages
  } = useGameStore();
  const [input, setInput] = useState("");
  const [loadingChat, setLoadingChat] = useState(false);
  const [error, setError] = useState("");
  const [tip, setTip] = useState("欢迎来到乡野絮语，使用方向键移动。");
  const [knownNpcs, setKnownNpcs] = useState<KnownNpc[]>([]);
  const [storyFragments, setStoryFragments] = useState<string[]>([]);
  const [rumors, setRumors] = useState<string[]>([]);
  const [recentEvents, setRecentEvents] = useState<PlayerEventItem[]>([]);
  const [autonomyState, setAutonomyState] = useState<NpcAutonomyState | null>(null);

  const currentRegion = useMemo(
    () => regions.find((region) => region.region_id === currentRegionId) ?? null,
    [regions, currentRegionId]
  );
  const activeNpcRegionName = useMemo(() => {
    if (!activeNpcProfile) {
      return "未知区域";
    }
    return (
      regions.find((region) => region.region_id === activeNpcProfile.region_id)?.region_name ?? "未知区域"
    );
  }, [regions, activeNpcProfile]);

  const nearbyNpcs = useMemo(
    () =>
      npcs.filter(
        (npc) => distance(playerPosition.x, playerPosition.y, npc.position.x, npc.position.y) <= 1
      ),
    [npcs, playerPosition.x, playerPosition.y]
  );
  const playerAvatar = useMemo(() => getPlayerAvatar(playerId), [playerId]);
  const activeNpcAvatar = useMemo(
    () => (activeNpc ? getNpcAvatar(activeNpc.name, activeNpc.role) : null),
    [activeNpc]
  );

  useEffect(() => {
    fetchRegions()
      .then((list) => {
        setRegions(list);
      })
      .catch(() => {
        setError("无法连接后端服务，请先启动 FastAPI。");
      });
  }, [setRegions]);

  useEffect(() => {
    getKnownNpcs(playerId)
      .then((items) => setKnownNpcs(items))
      .catch(() => {
        setKnownNpcs([]);
      });
  }, [playerId]);

  useEffect(() => {
    getPlayerProgress(playerId)
      .then((progress) => {
        setStoryFragments(progress.story_fragments);
        setRumors(progress.rumors);
        setRecentEvents(progress.recent_events);
      })
      .catch(() => {
        setError((prev) => prev || "读取探索进度失败。");
      });
  }, [playerId]);

  useEffect(() => {
    const regionId = findRegionId(playerPosition.x, playerPosition.y);
    if (regionId === currentRegionId) {
      return;
    }
    setCurrentRegion(regionId);
    if (!regionId) {
      return;
    }
    enterRegion(playerId, regionId)
      .then((res) => {
        addExploredRegion(regionId);
        upsertNpcs(res.npcs);
        const regionName = regions.find((r) => r.region_id === regionId)?.region_name ?? "未知区域";
        const fragmentTip = res.is_new_fragment ? " 你收集到一条村闻碎片。" : "";
        const rumorTip = res.is_new_rumor ? ` 你听到新传闻：${res.rumor_text}` : "";
        if (res.npc_generated && res.npcs[0]) {
          setTip(
            `你进入了${regionName}，遇见了${res.npcs[0].name}等${res.npcs.length}位村民。${res.event_text}${fragmentTip}${rumorTip}`
          );
        } else {
          setTip(`你回到了${regionName}。${res.event_text}${fragmentTip}${rumorTip}`);
        }
        getPlayerProgress(playerId)
          .then((progress) => {
            setStoryFragments(progress.story_fragments);
            setRumors(progress.rumors);
            setRecentEvents(progress.recent_events);
          })
          .catch(() => {
            setError((prev) => prev || "刷新探索进度失败。");
          });
      })
      .catch(() => {
        setError("区域探索请求失败。");
      });
  }, [
    playerId,
    playerPosition.x,
    playerPosition.y,
    currentRegionId,
    setCurrentRegion,
    addExploredRegion,
    upsertNpcs,
    regions
  ]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const key = event.key;
      if (!["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(key)) {
        return;
      }
      event.preventDefault();
      setError("");
      const next = { ...playerPosition };
      if (key === "ArrowUp") next.y -= 1;
      if (key === "ArrowDown") next.y += 1;
      if (key === "ArrowLeft") next.x -= 1;
      if (key === "ArrowRight") next.x += 1;
      next.x = Math.max(0, Math.min(GRID_WIDTH - 1, next.x));
      next.y = Math.max(0, Math.min(GRID_HEIGHT - 1, next.y));
      movePlayer(next.x, next.y);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [movePlayer, playerPosition]);

  async function openDialogue(npc: RegionEnterNpc) {
    setActiveNpc(npc);
    setAutonomyState(null);
    clearMessages();
    setSuggestions([]);
    try {
      const [profile, history, autonomy] = await Promise.all([
        getNpcProfile(npc.npc_id),
        getDialogueHistory(playerId, npc.npc_id),
        getNpcAutonomy(npc.npc_id)
      ]);
      setActiveNpcProfile(profile);
      setAutonomyState(autonomy);
      if (history.history.length > 0) {
        history.history.forEach((item, index) => {
          appendMessage({
            id: `${Date.now()}_history_${index}`,
            speaker: item.speaker,
            content: item.content
          });
        });
      } else {
        appendMessage({
          id: `${Date.now()}_opening`,
          speaker: "npc",
          content: npc.opening_line
        });
      }
    } catch {
      appendMessage({
        id: `${Date.now()}_opening`,
        speaker: "npc",
        content: npc.opening_line
      });
      setError("加载NPC信息失败。");
    }
  }

  async function sendChatMessage(message: string) {
    if (!activeNpc || !message.trim()) {
      return;
    }
    setLoadingChat(true);
    setError("");
    const content = message.trim();
    appendMessage({
      id: `${Date.now()}_player`,
      speaker: "player",
      content
    });
    setInput("");
    try {
      const res = await chatWithNpc(playerId, activeNpc.npc_id, content);
      appendMessage({
        id: `${Date.now()}_npc`,
        speaker: "npc",
        content: `${res.reply_text}（${res.emotion}）`
      });
      setSuggestions(res.suggestions);
      const profile = await getNpcProfile(activeNpc.npc_id);
      setActiveNpcProfile(profile);
      const autonomy = await getNpcAutonomy(activeNpc.npc_id);
      setAutonomyState(autonomy);
      const archive = await getKnownNpcs(playerId);
      setKnownNpcs(archive);
    } catch {
      setError("对话请求失败。");
    } finally {
      setLoadingChat(false);
    }
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await sendChatMessage(input);
  }

  return (
    <div className="layout">
      <section className="panel map-panel">
        <h1>乡野絮语</h1>
        <p className="tip">{tip}</p>
        <div
          className="map"
          style={{
            width: GRID_WIDTH * CELL_SIZE,
            height: GRID_HEIGHT * CELL_SIZE
          }}
        >
          {Array.from({ length: GRID_WIDTH * GRID_HEIGHT }).map((_, index) => {
            const x = index % GRID_WIDTH;
            const y = Math.floor(index / GRID_WIDTH);
            const regionId = findRegionId(x, y);
            return (
              <div
                key={`${x}_${y}`}
                className={`cell ${regionId ? "cell-active" : ""} ${
                  currentRegionId === regionId ? "cell-current" : ""
                }`}
                style={{
                  left: x * CELL_SIZE,
                  top: y * CELL_SIZE,
                  width: CELL_SIZE,
                  height: CELL_SIZE
                }}
              />
            );
          })}
          {npcs.map((npc) => (
            <button
              key={npc.npc_id}
              className={`npc ${nearbyNpcs.some((n) => n.npc_id === npc.npc_id) ? "npc-near" : ""}`}
              style={{
                left: npc.position.x * CELL_SIZE + 8,
                top: npc.position.y * CELL_SIZE + 8
              }}
              onClick={() => openDialogue(npc)}
            >
              <span className="token-emoji">{getNpcAvatar(npc.name, npc.role).emoji}</span>
            </button>
          ))}
          <div
            className={`player ${playerAvatar.tintClass}`}
            style={{
              left: playerPosition.x * CELL_SIZE + 8,
              top: playerPosition.y * CELL_SIZE + 8
            }}
          >
            <span className="token-emoji">{playerAvatar.emoji}</span>
          </div>
        </div>
        <div className="meta-row">
          <span>当前位置：{currentRegion?.region_name ?? "未命名区域"}</span>
          <span>已探索：{exploredRegions.length} 个区域</span>
          <span>已收集碎片：{storyFragments.length} 条</span>
        </div>
        {nearbyNpcs.length > 0 && (
          <div className="meta-row">
            <span>附近 NPC：</span>
            {nearbyNpcs.map((npc) => (
              <button key={npc.npc_id} className="link-btn" onClick={() => openDialogue(npc)}>
                {npc.name}
              </button>
            ))}
          </div>
        )}
        <div className="archive">
          <strong>最近见闻</strong>
          {recentEvents.length === 0 && <span className="subtle">暂无</span>}
          {recentEvents
            .slice()
            .reverse()
            .map((item) => (
              <span key={`${item.created_at}_${item.text}`} className="subtle">
                {item.text}
              </span>
            ))}
        </div>
      </section>
      <section className="panel chat-panel">
        <h2>对话</h2>
        <div className="archive">
          <strong>已认识 NPC</strong>
          {knownNpcs.length === 0 && <span className="subtle">暂无</span>}
          {knownNpcs.map((npc) => (
            <button
              key={npc.npc_id}
              className="archive-item"
              onClick={() =>
                openDialogue({
                  npc_id: npc.npc_id,
                  name: npc.name,
                  role: npc.role,
                  position: { x: 0, y: 0 },
                  opening_line: `${npc.name}看着你，像是记得你来过。`
                })
              }
            >
              <span>
                {npc.name} · {npc.role}
              </span>
              <span className="subtle">
                关系：{npc.relationship} · 已聊 {npc.chat_count} 次
              </span>
              <span className="subtle">{npc.memory_summary || "暂无记忆"}</span>
            </button>
          ))}
        </div>
        <div className="archive">
          <strong>故事碎片</strong>
          {storyFragments.length === 0 && <span className="subtle">暂无</span>}
          {storyFragments.map((fragment) => (
            <span key={fragment} className="subtle">
              {fragment}
            </span>
          ))}
        </div>
        <div className="archive">
          <strong>村中传闻</strong>
          {rumors.length === 0 && <span className="subtle">暂无</span>}
          {rumors.map((rumor) => (
            <span key={rumor} className="subtle">
              {rumor}
            </span>
          ))}
        </div>
        {!activeNpc && <p>靠近 NPC 后点击人物，或在“附近 NPC”里发起对话。</p>}
        {activeNpc && (
          <>
            <div className="npc-card">
              <div className="dialogue-head">
                <span className={`avatar-badge ${activeNpcAvatar?.tintClass ?? "avatar-mint"}`}>
                  {activeNpcAvatar?.emoji ?? "👤"}
                </span>
                <strong>
                  {activeNpc.name} · {activeNpc.role}
                </strong>
              </div>
              <span>{activeNpcProfile?.background ?? "加载中..."}</span>
              <span>所在区域：{activeNpcRegionName}</span>
              <span>性格：{activeNpcProfile?.personality.join(" / ") || "暂无"}</span>
              <span>当前情绪：{activeNpcProfile?.mood || "暂无"}</span>
              <span>最近互动：{formatTimeLabel(activeNpcProfile?.last_interaction_at ?? null)}</span>
              <span>记忆摘要：{activeNpcProfile?.memory_summary || "暂无"}</span>
              <span>自治记忆：{autonomyState?.autonomy_memory || "暂无"}</span>
              <span>
                世界进度：tick {autonomyState?.world_tick ?? "-"} · {autonomyState?.day_phase ?? "未知时段"}
              </span>
            </div>
            <div className="archive">
              <strong>NPC 行动日志</strong>
              {autonomyState?.recent_actions.length ? null : <span className="subtle">暂无</span>}
              {autonomyState?.recent_actions
                .slice()
                .reverse()
                .map((item) => (
                  <span key={`${item.created_at}_${item.tick}_${item.action_type}`} className="subtle">
                    {`tick${item.tick} · ${item.action_type} · ${item.action_text}`}
                  </span>
                ))}
            </div>
            <div className="archive">
              <strong>NPC 自治会话</strong>
              {autonomyState?.session_logs.length ? null : <span className="subtle">暂无</span>}
              {autonomyState?.session_logs
                .slice()
                .reverse()
                .map((item, index) => (
                  <span key={`${index}_${item}`} className="subtle">
                    {item}
                  </span>
                ))}
            </div>
            <div className="messages">
              {messages.map((message) => (
                <div
                  key={message.id}
                  className={`message-row ${message.speaker === "player" ? "row-player" : "row-npc"}`}
                >
                  <span
                    className={`chat-avatar ${
                      message.speaker === "player"
                        ? playerAvatar.tintClass
                        : activeNpcAvatar?.tintClass ?? "avatar-mint"
                    }`}
                  >
                    {message.speaker === "player"
                      ? playerAvatar.emoji
                      : (activeNpcAvatar?.emoji ?? "👤")}
                  </span>
                  <div className="message-block">
                    <span className="speaker-name">
                      {message.speaker === "player" ? "你" : activeNpc.name}
                    </span>
                    <div
                      className={`message ${
                        message.speaker === "player" ? "from-player" : "from-npc"
                      }`}
                    >
                      {message.content}
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <form onSubmit={onSubmit} className="chat-form">
              <input
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder="输入你想问的问题..."
                disabled={loadingChat}
              />
              <button type="submit" disabled={loadingChat || !input.trim()}>
                发送
              </button>
            </form>
            {suggestions.length > 0 && (
              <div className="suggestions">
                {suggestions.map((item) => (
                  <button key={item} className="suggestion-btn" onClick={() => sendChatMessage(item)}>
                    {item}
                  </button>
                ))}
              </div>
            )}
          </>
        )}
        {error && <p className="error">{error}</p>}
      </section>
    </div>
  );
}
