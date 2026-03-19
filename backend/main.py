from __future__ import annotations

from datetime import datetime
import json
import os
from random import Random
import re
from typing import Literal
from urllib import error, request

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv


load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))


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
    recent_events: list[PlayerEventItem]


class InMemoryGameStore:
    def __init__(self) -> None:
        self.random = Random(18)
        self.regions: dict[str, RegionConfig] = self._build_regions()
        self.region_npcs: dict[str, list[NpcProfile]] = {}
        self.player_explored: dict[str, set[str]] = {}
        self.dialogue_history: dict[tuple[str, str], list[tuple[str, str]]] = {}
        self.npc_index: dict[str, NpcProfile] = {}
        self.player_known_npcs: dict[str, set[str]] = {}
        self.player_story_fragments: dict[str, list[str]] = {}
        self.player_events: dict[str, list[PlayerEventItem]] = {}
        self.player_region_visits: dict[tuple[str, str], int] = {}
        self.llm_api_key = (
            os.getenv("LLM_API_KEY", "").strip()
            or os.getenv("OPENAI_API_KEY", "").strip()
            or os.getenv("API_KEY", "").strip()
        )
        self.llm_model = (
            os.getenv("LLM_MODEL", "").strip()
            or os.getenv("OPENAI_MODEL", "").strip()
            or "gpt-4o-mini"
        )
        explicit_llm_url = os.getenv("LLM_API_URL", "").strip()
        llm_base_url = (
            os.getenv("LLM_BASE_URL", "").strip()
            or os.getenv("OPENAI_BASE_URL", "").strip()
            or "https://api.openai.com/v1"
        )
        self.llm_api_url = explicit_llm_url or self._build_chat_completions_url(llm_base_url)

    def _build_regions(self) -> dict[str, RegionConfig]:
        region_data = [
            ("region_road_01", "村口小路", "村路", ["安静", "木栅栏"], [Position(x=2, y=2), Position(x=3, y=2)]),
            ("region_wheat_01", "麦田边缘", "麦田", ["麦浪", "微风"], [Position(x=7, y=1), Position(x=8, y=2)]),
            ("region_bridge_01", "河流木桥", "桥边", ["溪流", "木桥"], [Position(x=12, y=6), Position(x=11, y=6)]),
            ("region_orchard_01", "果园", "果园", ["果香", "蜂鸣"], [Position(x=4, y=9), Position(x=5, y=9)]),
            ("region_market_01", "村民集市", "集市", ["叫卖声", "人情味"], [Position(x=10, y=10), Position(x=9, y=10)]),
            ("region_teahouse_01", "山脚茶棚", "茶棚", ["茶香", "歇脚"], [Position(x=14, y=3), Position(x=13, y=3)]),
        ]
        return {
            region_id: RegionConfig(
                region_id=region_id,
                region_name=region_name,
                region_type=region_type,
                theme_tags=theme_tags,
                spawn_points=spawn_points,
            )
            for region_id, region_name, region_type, theme_tags, spawn_points in region_data
        }

    def enter_region(self, player_id: str, region_id: str) -> EnterRegionResponse:
        region = self.regions.get(region_id)
        if region is None:
            raise HTTPException(status_code=404, detail="区域不存在")
        explored = self.player_explored.setdefault(player_id, set())
        first_visit = region_id not in explored
        explored.add(region_id)
        visit_key = (player_id, region_id)
        self.player_region_visits[visit_key] = self.player_region_visits.get(visit_key, 0) + 1
        existing_npcs = self.region_npcs.get(region_id, [])
        npc_generated = False
        if not existing_npcs:
            npc_generated = True
            generated_npc = self._generate_npc(region)
            self.region_npcs[region_id] = [generated_npc]
            self.npc_index[generated_npc.npc_id] = generated_npc
            existing_npcs = [generated_npc]
        event_text = self._generate_region_event(region=region, first_visit=first_visit)
        story_fragment = self._build_story_fragment(region=region)
        story_bucket = self.player_story_fragments.setdefault(player_id, [])
        is_new_fragment = False
        if story_fragment not in story_bucket:
            story_bucket.append(story_fragment)
            is_new_fragment = True
        player_event = PlayerEventItem(created_at=datetime.utcnow(), text=event_text, region_id=region_id)
        self.player_events.setdefault(player_id, []).append(player_event)
        self.player_events[player_id] = self.player_events[player_id][-20:]
        return EnterRegionResponse(
            first_visit=first_visit,
            npc_generated=npc_generated,
            npcs=[
                EnterRegionResponseNpc(
                    npc_id=npc.npc_id,
                    name=npc.name,
                    role=npc.role,
                    position=npc.position,
                    opening_line=npc.opening_line,
                )
                for npc in existing_npcs
            ],
            event_text=event_text,
            story_fragment=story_fragment,
            is_new_fragment=is_new_fragment,
        )

    def _generate_npc(self, region: RegionConfig) -> NpcProfile:
        name_pool = ["阿禾", "小岚", "松伯", "阿柚", "青石", "柳婶", "阿槐", "阿桃"]
        role_pool = {
            "村路": ["赶集村民", "邮差", "修篱笆的木匠"],
            "麦田": ["年轻农夫", "看田老人", "拾穗姑娘"],
            "桥边": ["摆渡人", "钓鱼人", "挑水村民"],
            "果园": ["果农", "看园阿姨", "送果小哥"],
            "集市": ["杂货摊主", "豆花摊老板", "布料商"],
            "茶棚": ["茶棚掌柜", "说书人", "采茶人"],
        }
        personality_pool = ["温和", "健谈", "细心", "慢性子", "腼腆", "热心"]
        mood_pool = ["平静", "放松", "愉快", "专注"]
        name = self.random.choice(name_pool)
        role = self.random.choice(role_pool.get(region.region_type, ["村民"]))
        personality = self.random.sample(personality_pool, 3)
        mood = self.random.choice(mood_pool)
        opening_line = f"欢迎来到{region.region_name}，{region.theme_tags[0]}的感觉很适合慢慢走走。"
        background = f"{name}常年在{region.region_name}活动，对这里的景色和村里传闻都很熟悉。"
        llm_card = self._generate_npc_by_llm(region)
        if llm_card:
            name = llm_card.get("name", name)
            role = llm_card.get("role", role)
            personality_value = llm_card.get("personality")
            if isinstance(personality_value, list) and personality_value:
                personality = [str(item) for item in personality_value[:3]]
            mood = str(llm_card.get("mood", mood))
            opening_line = str(llm_card.get("opening_line", opening_line))
            background = str(llm_card.get("background", background))
        npc_id = f"npc_{region.region_id.split('_')[-1]}_{self.random.randint(100, 999)}"
        return NpcProfile(
            npc_id=npc_id,
            region_id=region.region_id,
            name=name,
            role=role,
            personality=personality,
            mood=mood,
            location=region.region_name,
            background=background,
            opening_line=opening_line,
            position=self.random.choice(region.spawn_points),
        )

    def chat(self, player_id: str, npc_id: str, message: str) -> DialogueChatResponse:
        npc = self.npc_index.get(npc_id)
        if npc is None:
            raise HTTPException(status_code=404, detail="NPC不存在")
        normalized_message = message.strip()
        if not normalized_message:
            raise HTTPException(status_code=400, detail="对话内容不能为空")
        known_npcs = self.player_known_npcs.setdefault(player_id, set())
        known_npcs.add(npc_id)
        history_key = (player_id, npc_id)
        history = self.dialogue_history.setdefault(history_key, [])
        history.append(("player", normalized_message))
        trimmed_history = history[-6:]
        history_keywords = "、".join(
            text[:8] for speaker, text in trimmed_history if speaker == "player"
        )
        llm_text_reply: str | None = None
        llm_result = self._chat_by_llm(npc=npc, player_message=normalized_message, history=trimmed_history)
        if llm_result:
            reply_text = str(llm_result.get("reply_text", "")).strip()
            emotion = str(llm_result.get("emotion", "")).strip() or self._decide_emotion(normalized_message)
            raw_suggestions = llm_result.get("suggestions", [])
            suggestions = (
                [str(item) for item in raw_suggestions[:2]]
                if isinstance(raw_suggestions, list) and raw_suggestions
                else self._suggest_topics(npc.region_id)
            )
            memory_update = str(llm_result.get("memory_update", "")).strip()
            if not reply_text:
                llm_text_reply = self._chat_text_by_llm(
                    npc=npc,
                    player_message=normalized_message,
                    history=trimmed_history,
                )
                reply_text = llm_text_reply
            if not memory_update:
                memory_update = f"玩家最近聊到：{history_keywords}" if history_keywords else "玩家初次交流"
        else:
            llm_text_reply = self._chat_text_by_llm(
                npc=npc,
                player_message=normalized_message,
                history=trimmed_history,
            )
            reply_text = llm_text_reply
            emotion = self._decide_emotion(normalized_message)
            suggestions = self._suggest_topics(npc.region_id)
            memory_update = f"玩家最近聊到：{history_keywords}" if history_keywords else "玩家初次交流"
        if not reply_text:
            raise HTTPException(status_code=503, detail="LLM对话生成失败，请稍后重试")
        npc.memory_summary = memory_update
        npc.last_interaction_at = datetime.utcnow()
        history.append(("npc", reply_text))
        self.dialogue_history[history_key] = history[-10:]
        return DialogueChatResponse(reply_text=reply_text[:80], emotion=emotion, suggestions=suggestions)

    def _decide_emotion(self, message: str) -> Literal["平静", "愉快", "好奇", "关心"]:
        if "吗" in message:
            return "好奇"
        if "谢谢" in message:
            return "愉快"
        if "难过" in message or "烦" in message:
            return "关心"
        return "平静"

    def _suggest_topics(self, region_id: str) -> list[str]:
        mapping: dict[str, list[str]] = {
            "region_road_01": ["村口最近有什么变化？", "从这条路往哪边风景最好？"],
            "region_wheat_01": ["麦田什么时候最美？", "这附近还有谁常来？"],
            "region_bridge_01": ["桥那边通向哪里？", "河边晚上会热闹吗？"],
            "region_orchard_01": ["果园现在有什么果子？", "你最喜欢哪棵树？"],
            "region_market_01": ["集市什么时候最热闹？", "这里有什么必买的小吃？"],
            "region_teahouse_01": ["茶棚有什么招牌茶？", "山路好走吗？"],
        }
        return mapping.get(region_id, ["这附近还有什么有趣的地方？", "你平时都在做什么？"])

    def _call_llm_json(self, system_prompt: str, user_prompt: str) -> dict | None:
        if not self.llm_api_url or not self.llm_api_key:
            return None
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        payloads = [
            {
                "model": self.llm_model,
                "messages": messages,
                "temperature": 0.7,
                "response_format": {"type": "json_object"},
            },
            {
                "model": self.llm_model,
                "messages": messages,
                "temperature": 0.7,
            },
        ]
        for payload in payloads:
            body = self._post_llm(payload)
            if not body:
                continue
            parsed = self._parse_llm_response_body(body)
            if parsed:
                return parsed
        return None

    def _post_llm(self, payload: dict) -> str | None:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.llm_api_key}",
        }
        req = request.Request(
            self.llm_api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=20) as resp:
                return resp.read().decode("utf-8")
        except (error.URLError, TimeoutError, ValueError):
            return None

    def _parse_llm_response_body(self, body: str) -> dict | None:
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return None
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return None
        return self._parse_llm_content(content)

    def _parse_llm_content(self, content: object) -> dict | None:
        if isinstance(content, dict):
            return content
        if isinstance(content, list):
            text_chunks = []
            for item in content:
                if isinstance(item, dict):
                    value = item.get("text")
                    if value:
                        text_chunks.append(str(value))
            content = "".join(text_chunks)
        if not isinstance(content, str):
            return None
        normalized = content.strip()
        if not normalized:
            return None
        try:
            parsed = json.loads(normalized)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            json_text = self._extract_json_object(normalized)
            if not json_text:
                return None
            try:
                parsed = json.loads(json_text)
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                return None

    def _extract_json_object(self, content: str) -> str | None:
        fenced_blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)```", content, flags=re.IGNORECASE)
        for block in fenced_blocks:
            candidate = block.strip()
            if candidate.startswith("{") and candidate.endswith("}"):
                return candidate
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            return content[start : end + 1].strip()
        return None

    def _call_llm_text(self, system_prompt: str, user_prompt: str) -> str | None:
        if not self.llm_api_url or not self.llm_api_key:
            return None
        payload = {
            "model": self.llm_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.7,
        }
        body = self._post_llm(payload)
        if not body:
            return None
        return self._parse_llm_text_response_body(body)

    def _parse_llm_text_response_body(self, body: str) -> str | None:
        try:
            data = json.loads(body)
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError):
            return None
        return self._flatten_llm_content(content)

    def _flatten_llm_content(self, content: object) -> str | None:
        if isinstance(content, str):
            normalized = content.strip()
            if not normalized:
                return None
            parsed_json = self._parse_llm_content(normalized)
            if parsed_json:
                value = str(parsed_json.get("reply_text", "")).strip()
                return value or None
            return normalized
        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                if isinstance(item, str):
                    value = item.strip()
                    if value:
                        chunks.append(value)
                elif isinstance(item, dict):
                    text = str(item.get("text", "")).strip()
                    if text:
                        chunks.append(text)
            joined = "".join(chunks).strip()
            if not joined:
                return None
            parsed_json = self._parse_llm_content(joined)
            if parsed_json:
                value = str(parsed_json.get("reply_text", "")).strip()
                return value or None
            return joined
        if isinstance(content, dict):
            value = str(content.get("reply_text", "")).strip()
            return value or None
        return None

    def _build_chat_completions_url(self, base_url: str) -> str:
        normalized = base_url.strip().rstrip("/")
        if not normalized:
            return ""
        if normalized.endswith("/chat/completions"):
            return normalized
        if normalized.endswith("/v1"):
            return f"{normalized}/chat/completions"
        return f"{normalized}/v1/chat/completions"

    def _generate_npc_by_llm(self, region: RegionConfig) -> dict | None:
        system_prompt = (
            "你是乡村探索游戏的NPC生成器。"
            "只输出JSON，字段必须包含name,role,personality,mood,background,opening_line。"
            "人物设定简洁真实，不要超自然。"
        )
        user_prompt = (
            f"区域名:{region.region_name}\n"
            f"区域类型:{region.region_type}\n"
            f"风格标签:{'、'.join(region.theme_tags)}\n"
            "请生成一个适合该区域的NPC。"
        )
        return self._call_llm_json(system_prompt, user_prompt)

    def _generate_region_event(self, region: RegionConfig, first_visit: bool) -> str:
        llm_event = self._generate_region_event_by_llm(region=region, first_visit=first_visit)
        if llm_event:
            value = str(llm_event.get("event_text", "")).strip()
            if value:
                return value[:80]
        openers = ["你听见", "你注意到", "你看到", "你闻到"]
        details = {
            "村路": ["远处有车轮压过泥路的声音。", "篱笆边挂着刚晒好的草帽。"],
            "麦田": ["风吹过麦穗，像一阵轻轻的海浪。", "田埂上有人留下新鲜的脚印。"],
            "桥边": ["桥下水流清亮，石头上反着日光。", "木桥轻轻晃动，像在提醒你慢一点。"],
            "果园": ["果树间有熟果落地的闷响。", "枝叶里藏着一阵淡淡甜香。"],
            "集市": ["摊贩叫卖声此起彼伏。", "锅里的热气裹着豆香飘了过来。"],
            "茶棚": ["茶汤的香气顺着风飘过来。", "棚下的木凳被阳光晒得暖暖的。"],
        }
        opener = self.random.choice(openers)
        tail = self.random.choice(details.get(region.region_type, ["村里一切都在慢慢流动。"]))
        if first_visit:
            return f"{opener}{tail}"
        return f"你再次来到{region.region_name}，{tail}"

    def _generate_region_event_by_llm(self, region: RegionConfig, first_visit: bool) -> dict | None:
        system_prompt = (
            "你是乡村探索游戏的事件文案生成器。"
            "只输出JSON，字段必须包含event_text。"
            "文本不超过70字，温暖自然。"
        )
        user_prompt = (
            f"区域名:{region.region_name}\n"
            f"区域类型:{region.region_type}\n"
            f"风格标签:{'、'.join(region.theme_tags)}\n"
            f"是否首次进入:{'是' if first_visit else '否'}"
        )
        return self._call_llm_json(system_prompt, user_prompt)

    def _build_story_fragment(self, region: RegionConfig) -> str:
        samples = {
            "村路": "村口老榆树下，常有人交换远方消息。",
            "麦田": "有人说，麦浪最亮的时候，愿望更容易被风听见。",
            "桥边": "木桥上刻着模糊的名字，像是很久以前的约定。",
            "果园": "果园看守人总会把最甜的一颗留给晚来的人。",
            "集市": "集市尽头的摊位，偶尔会出现不常见的手工小物。",
            "茶棚": "茶棚老板记得每位过客爱喝的第一口茶温。",
        }
        return samples.get(region.region_type, "村里每天都在长出新的传闻。")

    def _chat_by_llm(
        self,
        npc: NpcProfile,
        player_message: str,
        history: list[tuple[str, str]],
    ) -> dict | None:
        history_text = "\n".join(f"{speaker}:{text}" for speaker, text in history[-6:])
        system_prompt = (
            "你是乡村小游戏中的NPC，必须保持角色设定一致，"
            "回复简洁自然，中文不超过80字。"
            "输出JSON字段:reply_text,emotion,suggestions,memory_update。"
        )
        user_prompt = (
            f"NPC姓名:{npc.name}\n"
            f"职业:{npc.role}\n"
            f"性格:{'、'.join(npc.personality)}\n"
            f"心情:{npc.mood}\n"
            f"地点:{npc.location}\n"
            f"背景:{npc.background}\n"
            f"记忆摘要:{npc.memory_summary or '暂无'}\n"
            f"历史对话:\n{history_text}\n"
            f"玩家输入:{player_message}\n"
            "请给出回应。"
        )
        return self._call_llm_json(system_prompt, user_prompt)

    def _chat_text_by_llm(
        self,
        npc: NpcProfile,
        player_message: str,
        history: list[tuple[str, str]],
    ) -> str | None:
        history_text = "\n".join(f"{speaker}:{text}" for speaker, text in history[-6:])
        system_prompt = (
            "你是乡村小游戏中的NPC，必须保持角色设定一致，"
            "请直接回复自然中文，不要JSON，不超过80字。"
        )
        user_prompt = (
            f"NPC姓名:{npc.name}\n"
            f"职业:{npc.role}\n"
            f"性格:{'、'.join(npc.personality)}\n"
            f"心情:{npc.mood}\n"
            f"地点:{npc.location}\n"
            f"背景:{npc.background}\n"
            f"记忆摘要:{npc.memory_summary or '暂无'}\n"
            f"历史对话:\n{history_text}\n"
            f"玩家输入:{player_message}\n"
            "只输出一句NPC回复。"
        )
        return self._call_llm_text(system_prompt, user_prompt)

    def get_npc(self, npc_id: str) -> NpcDetailResponse:
        npc = self.npc_index.get(npc_id)
        if npc is None:
            raise HTTPException(status_code=404, detail="NPC不存在")
        return NpcDetailResponse(
            npc_id=npc.npc_id,
            name=npc.name,
            role=npc.role,
            personality=npc.personality,
            mood=npc.mood,
            background=npc.background,
            memory_summary=npc.memory_summary,
            region_id=npc.region_id,
            last_interaction_at=npc.last_interaction_at,
        )

    def get_dialogue_history(self, player_id: str, npc_id: str) -> DialogueHistoryResponse:
        history = self.dialogue_history.get((player_id, npc_id), [])
        return DialogueHistoryResponse(
            player_id=player_id,
            npc_id=npc_id,
            history=[DialogueHistoryItem(speaker=speaker, content=content) for speaker, content in history],
        )

    def get_known_npcs(self, player_id: str) -> list[KnownNpcResponse]:
        known_npc_ids = self.player_known_npcs.get(player_id, set())
        result = []
        for npc_id in known_npc_ids:
            npc = self.npc_index.get(npc_id)
            if npc is None:
                continue
            result.append(
                KnownNpcResponse(
                    npc_id=npc.npc_id,
                    name=npc.name,
                    role=npc.role,
                    region_id=npc.region_id,
                    memory_summary=npc.memory_summary,
                    relationship=self._relationship_label(player_id=player_id, npc_id=npc.npc_id),
                    chat_count=self._chat_count(player_id=player_id, npc_id=npc.npc_id),
                    last_interaction_at=npc.last_interaction_at,
                )
            )
        result.sort(
            key=lambda item: item.last_interaction_at or datetime.min,
            reverse=True,
        )
        return result

    def _chat_count(self, player_id: str, npc_id: str) -> int:
        history = self.dialogue_history.get((player_id, npc_id), [])
        return len([speaker for speaker, _ in history if speaker == "player"])

    def _relationship_label(self, player_id: str, npc_id: str) -> Literal["陌生", "点头之交", "熟悉", "信任"]:
        count = self._chat_count(player_id=player_id, npc_id=npc_id)
        if count <= 0:
            return "陌生"
        if count <= 2:
            return "点头之交"
        if count <= 5:
            return "熟悉"
        return "信任"

    def get_player_progress(self, player_id: str) -> PlayerProgressResponse:
        explored = sorted(self.player_explored.get(player_id, set()))
        fragments = self.player_story_fragments.get(player_id, [])
        events = self.player_events.get(player_id, [])[-8:]
        return PlayerProgressResponse(
            player_id=player_id,
            explored_region_ids=explored,
            story_fragments=fragments,
            recent_events=events,
        )


store = InMemoryGameStore()
app = FastAPI(title="乡野絮语 API", version="0.1.0")
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


@app.get("/api/dialogue/history", response_model=DialogueHistoryResponse)
def get_dialogue_history(player_id: str, npc_id: str) -> DialogueHistoryResponse:
    return store.get_dialogue_history(player_id=player_id, npc_id=npc_id)


@app.get("/api/player/{player_id}/npcs", response_model=list[KnownNpcResponse])
def get_player_npcs(player_id: str) -> list[KnownNpcResponse]:
    return store.get_known_npcs(player_id=player_id)


@app.get("/api/player/{player_id}/progress", response_model=PlayerProgressResponse)
def get_player_progress(player_id: str) -> PlayerProgressResponse:
    return store.get_player_progress(player_id=player_id)
