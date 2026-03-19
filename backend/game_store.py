from __future__ import annotations

from datetime import datetime
from random import Random
from typing import Literal

from fastapi import HTTPException

from llm_client import LlmClient
from schemas import (
    DialogueChatResponse,
    DialogueHistoryItem,
    DialogueHistoryResponse,
    EnterRegionResponse,
    EnterRegionResponseNpc,
    KnownNpcResponse,
    NpcAutonomyActionItem,
    NpcAutonomyStateResponse,
    NpcDetailResponse,
    NpcProfile,
    PlayerEventItem,
    PlayerProgressResponse,
    Position,
    RegionConfig,
)


class InMemoryGameStore:
    def __init__(self) -> None:
        self.random = Random(18)
        self.llm = LlmClient()
        self.world_tick = 0
        self.regions: dict[str, RegionConfig] = self._build_regions()
        self.region_npcs: dict[str, list[NpcProfile]] = {}
        self.player_explored: dict[str, set[str]] = {}
        self.dialogue_history: dict[tuple[str, str], list[tuple[str, str]]] = {}
        self.npc_index: dict[str, NpcProfile] = {}
        self.npc_autonomy_memory: dict[str, str] = {}
        self.npc_autonomy_sessions: dict[str, list[str]] = {}
        self.npc_autonomy_actions: dict[str, list[NpcAutonomyActionItem]] = {}
        self.npc_external_signals: dict[str, list[str]] = {}
        self.npc_action_cooldown_until: dict[str, dict[str, int]] = {}
        self.npc_last_world_tick: dict[str, int] = {}
        self.player_known_npcs: dict[str, set[str]] = {}
        self.player_story_fragments: dict[str, list[str]] = {}
        self.player_rumors: dict[str, list[str]] = {}
        self.player_events: dict[str, list[PlayerEventItem]] = {}
        self.player_region_visits: dict[tuple[str, str], int] = {}

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
            target_count = self._region_npc_count(region)
            generated_npcs = [self._generate_npc(region) for _ in range(target_count)]
            self.region_npcs[region_id] = generated_npcs
            for npc in generated_npcs:
                self.npc_index[npc.npc_id] = npc
                self.npc_autonomy_memory[npc.npc_id] = f"{npc.name}关注{region.region_name}的日常变化。"
                self.npc_autonomy_sessions[npc.npc_id] = [f"{npc.name}在{region.region_name}开始了今天的观察。"]
                self.npc_autonomy_actions[npc.npc_id] = []
                self.npc_external_signals[npc.npc_id] = []
                self.npc_action_cooldown_until[npc.npc_id] = {}
            existing_npcs = generated_npcs
        event_text = self._generate_region_event(region=region, first_visit=first_visit)
        story_fragment = self._build_story_fragment(region=region)
        story_bucket = self.player_story_fragments.setdefault(player_id, [])
        is_new_fragment = False
        if story_fragment not in story_bucket:
            story_bucket.append(story_fragment)
            is_new_fragment = True
        rumor_text = self._generate_region_rumor(region=region)
        rumor_bucket = self.player_rumors.setdefault(player_id, [])
        is_new_rumor = False
        if rumor_text and rumor_text not in rumor_bucket:
            rumor_bucket.append(rumor_text)
            self.player_rumors[player_id] = rumor_bucket[-20:]
            is_new_rumor = True
        player_event = PlayerEventItem(created_at=datetime.utcnow(), text=event_text, region_id=region_id)
        self.player_events.setdefault(player_id, []).append(player_event)
        self.player_events[player_id] = self.player_events[player_id][-20:]
        self._run_world_tick(player_id=player_id, current_region_id=region_id)
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
            rumor_text=rumor_text,
            is_new_rumor=is_new_rumor,
        )

    def _region_npc_count(self, region: RegionConfig) -> int:
        mapping = {
            "村路": 2,
            "麦田": 2,
            "桥边": 2,
            "果园": 2,
            "集市": 3,
            "茶棚": 2,
        }
        return mapping.get(region.region_type, 2)

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
            name = str(llm_card.get("name", name))
            role = str(llm_card.get("role", role))
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
        self._run_world_tick(player_id=player_id, current_region_id=npc.region_id)
        return DialogueChatResponse(reply_text=reply_text[:80], emotion=emotion, suggestions=suggestions)

    def _run_world_tick(self, player_id: str, current_region_id: str | None) -> None:
        self.world_tick += 1
        npcs = list(self.npc_index.values())
        npcs.sort(key=lambda item: 0 if item.region_id == current_region_id else 1)
        for npc in npcs:
            last_tick = self.npc_last_world_tick.get(npc.npc_id, 0)
            if self.world_tick - last_tick < 2 and npc.region_id != current_region_id:
                continue
            plan = self._plan_npc_action(
                npc=npc,
                player_id=player_id,
                current_region_id=current_region_id,
            )
            if plan:
                self._execute_npc_action(npc=npc, plan=plan, player_id=player_id)
            self.npc_last_world_tick[npc.npc_id] = self.world_tick

    def _plan_npc_action(
        self,
        npc: NpcProfile,
        player_id: str,
        current_region_id: str | None,
    ) -> dict | None:
        day_phase = self._day_phase()
        autonomy_memory = self.npc_autonomy_memory.get(npc.npc_id, "暂无")
        autonomy_session = self.npc_autonomy_sessions.get(npc.npc_id, [])
        social_signals = self.npc_external_signals.get(npc.npc_id, [])
        recent_session = "\n".join(autonomy_session[-4:]) or "暂无"
        recent_signals = "\n".join(social_signals[-3:]) or "暂无"
        known_count = len(self.player_known_npcs.get(player_id, set()))
        world_info = (
            f"世界区域数:{len(self.regions)}\n"
            f"玩家当前区域:{current_region_id or '未知'}\n"
            f"玩家已认识NPC数:{known_count}\n"
            f"当前世界tick:{self.world_tick}\n"
            f"当前时段:{day_phase}"
        )
        system_prompt = (
            "你是乡村小游戏中的NPC自治决策器。"
            "仅输出JSON，字段:action_type,action_text,target_region_id,event_text,rumor_text,memory_update。"
            "action_type只能是idle/move/share_rumor/create_event。"
            "动作应朴素、低风险、符合乡村生活。"
        )
        user_prompt = (
            f"NPC姓名:{npc.name}\n"
            f"职业:{npc.role}\n"
            f"性格:{'、'.join(npc.personality)}\n"
            f"当前区域:{npc.region_id}\n"
            f"背景:{npc.background}\n"
            f"自治记忆:{autonomy_memory}\n"
            f"自治会话:\n{recent_session}\n"
            f"同伴影响:\n{recent_signals}\n"
            f"世界信息:\n{world_info}\n"
            "请输出下一步动作。"
        )
        return self.llm.call_json(system_prompt, user_prompt)

    def _execute_npc_action(self, npc: NpcProfile, plan: dict, player_id: str) -> None:
        action_type = self._normalize_action_type(str(plan.get("action_type", "")).strip() or "idle")
        action_text = str(plan.get("action_text", "")).strip()
        event_text = str(plan.get("event_text", "")).strip()
        rumor_text = str(plan.get("rumor_text", "")).strip()
        memory_update = str(plan.get("memory_update", "")).strip()
        target_region_id = str(plan.get("target_region_id", "")).strip()
        action_type, action_text = self._apply_action_policy(npc=npc, action_type=action_type, action_text=action_text)
        if action_type == "move":
            target_region = self.regions.get(target_region_id) if target_region_id else None
            if target_region is None:
                target_region = self.regions.get(npc.region_id)
            if self._day_phase() == "夜晚" and target_region and target_region.region_id != npc.region_id:
                target_region = self.regions.get(npc.region_id)
            if target_region:
                old_region_id = npc.region_id
                old_list = self.region_npcs.get(old_region_id, [])
                self.region_npcs[old_region_id] = [item for item in old_list if item.npc_id != npc.npc_id]
                npc.region_id = target_region.region_id
                npc.location = target_region.region_name
                npc.position = self.random.choice(target_region.spawn_points)
                self.region_npcs.setdefault(target_region.region_id, []).append(npc)
                if not event_text:
                    event_text = f"{npc.name}从{self.regions[old_region_id].region_name}走到了{target_region.region_name}。"
        if action_type == "share_rumor":
            if not rumor_text:
                region = self.regions.get(npc.region_id)
                if region:
                    rumor_text = self._generate_region_rumor(region=region)
            if rumor_text:
                rumor_bucket = self.player_rumors.setdefault(player_id, [])
                if rumor_text not in rumor_bucket:
                    rumor_bucket.append(rumor_text)
                    self.player_rumors[player_id] = rumor_bucket[-20:]
            if not event_text and rumor_text:
                event_text = f"{npc.name}悄悄提到：{rumor_text}"
        if action_type == "create_event" and not event_text:
            event_text = f"{npc.name}忙着{action_text or '处理手头小事'}。"
        if event_text:
            self.player_events.setdefault(player_id, []).append(
                PlayerEventItem(created_at=datetime.utcnow(), text=event_text[:80], region_id=npc.region_id)
            )
            self.player_events[player_id] = self.player_events[player_id][-20:]
        if action_text:
            self.npc_autonomy_sessions.setdefault(npc.npc_id, []).append(
                f"tick{self.world_tick}:{action_type}:{action_text}"
            )
            self.npc_autonomy_sessions[npc.npc_id] = self.npc_autonomy_sessions[npc.npc_id][-12:]
        if memory_update:
            self.npc_autonomy_memory[npc.npc_id] = memory_update[:120]
        normalized_action_text = action_text or event_text or "保持观察"
        self.npc_autonomy_actions.setdefault(npc.npc_id, []).append(
            NpcAutonomyActionItem(
                created_at=datetime.utcnow(),
                tick=self.world_tick,
                action_type=self._normalize_action_type(action_type),
                action_text=normalized_action_text[:80],
                region_id=npc.region_id,
            )
        )
        self.npc_autonomy_actions[npc.npc_id] = self.npc_autonomy_actions[npc.npc_id][-12:]
        self._broadcast_npc_influence(
            npc=npc,
            action_type=action_type,
            action_text=normalized_action_text,
            rumor_text=rumor_text,
            event_text=event_text,
        )

    def _apply_action_policy(
        self,
        npc: NpcProfile,
        action_type: Literal["idle", "move", "share_rumor", "create_event"],
        action_text: str,
    ) -> tuple[Literal["idle", "move", "share_rumor", "create_event"], str]:
        cooldown_rules = {"move": 2, "share_rumor": 3, "create_event": 2, "idle": 0}
        preferred = [action_type, "share_rumor", "create_event", "move", "idle"]
        selected = "idle"
        cooldown_map = self.npc_action_cooldown_until.setdefault(npc.npc_id, {})
        for candidate in preferred:
            normalized = self._normalize_action_type(candidate)
            until_tick = cooldown_map.get(normalized, 0)
            if self.world_tick >= until_tick:
                selected = normalized
                break
        if selected == "move" and self._day_phase() == "夜晚":
            selected = "idle"
        if selected != "idle":
            cooldown_map[selected] = self.world_tick + cooldown_rules[selected]
        if selected == "idle" and not action_text:
            return selected, "观察村里的动静"
        if selected != action_type and not action_text:
            return selected, "等待合适时机再行动"
        return selected, action_text

    def _broadcast_npc_influence(
        self,
        npc: NpcProfile,
        action_type: Literal["idle", "move", "share_rumor", "create_event"],
        action_text: str,
        rumor_text: str,
        event_text: str,
    ) -> None:
        peers = [item for item in self.region_npcs.get(npc.region_id, []) if item.npc_id != npc.npc_id]
        if not peers:
            return
        if action_type == "share_rumor" and rumor_text:
            influence_text = f"{npc.name}提到新传闻：{rumor_text[:50]}"
        elif action_type == "move":
            influence_text = f"{npc.name}离开后留下话题：{action_text[:40]}"
        elif action_type == "create_event":
            influence_text = f"{npc.name}引发了动静：{(event_text or action_text)[:50]}"
        else:
            influence_text = f"{npc.name}保持观察：{action_text[:40]}"
        for peer in peers:
            self.npc_external_signals.setdefault(peer.npc_id, []).append(influence_text)
            self.npc_external_signals[peer.npc_id] = self.npc_external_signals[peer.npc_id][-8:]
            self.npc_autonomy_sessions.setdefault(peer.npc_id, []).append(
                f"tick{self.world_tick}:同伴影响:{influence_text}"
            )
            self.npc_autonomy_sessions[peer.npc_id] = self.npc_autonomy_sessions[peer.npc_id][-12:]
            memory_prefix = self.npc_autonomy_memory.get(peer.npc_id, "")
            merged_memory = f"{memory_prefix}；{influence_text}".strip("；")
            self.npc_autonomy_memory[peer.npc_id] = merged_memory[-120:]

    def _normalize_action_type(self, action_type: str) -> Literal["idle", "move", "share_rumor", "create_event"]:
        allowed = {"idle", "move", "share_rumor", "create_event"}
        if action_type in allowed:
            return action_type
        return "idle"

    def _day_phase(self) -> Literal["清晨", "白昼", "黄昏", "夜晚"]:
        phases = ["清晨", "白昼", "黄昏", "夜晚"]
        return phases[self.world_tick % len(phases)]

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
        return self.llm.call_json(system_prompt, user_prompt)

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
        return self.llm.call_json(system_prompt, user_prompt)

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

    def _generate_region_rumor(self, region: RegionConfig) -> str:
        llm_rumor = self._generate_region_rumor_by_llm(region=region)
        if llm_rumor:
            value = str(llm_rumor.get("rumor_text", "")).strip()
            if value:
                return value[:80]
        rumor_pool = {
            "村路": ["听说傍晚会有外乡商队经过村口。", "有人说老榆树旁埋着一封旧信。"],
            "麦田": ["村里传闻今年第一穗金麦会带来好运。", "听说田埂尽头有一块从不积水的地。"],
            "桥边": ["有人说木桥下偶尔会漂来刻字木片。", "传闻夜里桥边能听见旧船铃声。"],
            "果园": ["听说果园最北边那棵树每年最先结果。", "有人说蜂群总会绕着一条旧石路飞。"],
            "集市": ["传闻集市末尾摊位会随机出现稀罕手作。", "听说中午前后有位老人会卖旧地图。"],
            "茶棚": ["有人说茶棚后山有条近路能看见整片村庄。", "听说掌柜收藏着一套失传茶具。"],
        }
        return self.random.choice(rumor_pool.get(region.region_type, ["村里又冒出一条新传闻。"]))

    def _generate_region_rumor_by_llm(self, region: RegionConfig) -> dict | None:
        system_prompt = (
            "你是乡村探索游戏的传闻生成器。"
            "只输出JSON，字段必须包含rumor_text。"
            "传闻要可信、朴素、有生活气息，不超过70字。"
        )
        user_prompt = (
            f"区域名:{region.region_name}\n"
            f"区域类型:{region.region_type}\n"
            f"风格标签:{'、'.join(region.theme_tags)}"
        )
        return self.llm.call_json(system_prompt, user_prompt)

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
        return self.llm.call_json(system_prompt, user_prompt)

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
        return self.llm.call_text(system_prompt, user_prompt)

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

    def get_npc_autonomy(self, npc_id: str) -> NpcAutonomyStateResponse:
        npc = self.npc_index.get(npc_id)
        if npc is None:
            raise HTTPException(status_code=404, detail="NPC不存在")
        session_logs = self.npc_autonomy_sessions.get(npc_id, [])
        actions = self.npc_autonomy_actions.get(npc_id, [])
        return NpcAutonomyStateResponse(
            npc_id=npc_id,
            world_tick=self.world_tick,
            day_phase=self._day_phase(),
            autonomy_memory=self.npc_autonomy_memory.get(npc_id, npc.memory_summary or "暂无"),
            session_logs=session_logs[-8:],
            recent_actions=actions[-6:],
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
        rumors = self.player_rumors.get(player_id, [])
        events = self.player_events.get(player_id, [])[-8:]
        return PlayerProgressResponse(
            player_id=player_id,
            explored_region_ids=explored,
            story_fragments=fragments,
            rumors=rumors,
            recent_events=events,
        )
