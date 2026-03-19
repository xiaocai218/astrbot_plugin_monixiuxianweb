# managers/adventure_manager.py
"""历练系统管理器。"""

import json
import random
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from astrbot.api import logger

from ..battle_hp_utils import ADVENTURE_ROUTE_COOLDOWNS_KEY
from ..data.data_manager import DataBase
from ..models import Player
from ..models_extended import UserCd, UserStatus

if TYPE_CHECKING:
    from ..core import StorageRingManager


class AdventureManager:
    """处理历练路线、事件、掉落与结算。"""

    CONFIG_FILE = Path(__file__).resolve().parents[1] / "config" / "adventure_config.json"

    DEFAULT_CONFIG = {
        "routes": [
            {
                "key": "scout",
                "name": "巡山问道",
                "aliases": ["短途", "巡山", "巡山问道", "巡逻", "short"],
                "description": "巡视宗门周边，风险较低，适合积累经验。",
                "risk": "低",
                "duration": 1800,
                "min_level": 0,
                "fatigue_cooldown": 300,
                "base_exp_per_min": 45,
                "base_gold_per_min": 10,
                "level_bonus_exp": 12,
                "level_bonus_gold": 3,
                "completion_bonus": {"exp": 300, "gold": 120},
                "event_weights": {"safe": 60, "standard": 30, "risky": 10},
                "drop_tier": "low",
                "bounty_tag": "adventure_scout",
                "bounty_progress": 1,
            },
            {
                "key": "journey",
                "name": "云游四方",
                "aliases": ["中途", "云游", "云游四方", "游历", "medium"],
                "description": "行走各地山川，收益稳定，偶有奇遇。",
                "risk": "中",
                "duration": 3600,
                "min_level": 3,
                "fatigue_cooldown": 600,
                "base_exp_per_min": 55,
                "base_gold_per_min": 14,
                "level_bonus_exp": 18,
                "level_bonus_gold": 5,
                "completion_bonus": {"exp": 500, "gold": 180},
                "event_weights": {"safe": 35, "standard": 45, "risky": 20},
                "drop_tier": "mid",
                "bounty_tag": "adventure_roam",
                "bounty_progress": 1,
            },
            {
                "key": "hunt",
                "name": "猎魔肃清",
                "aliases": ["长途", "猎魔", "肃清", "猎魔肃清", "hunt", "long"],
                "description": "深入妖兽巢穴清剿邪祟，收益可观，但战斗更频繁。",
                "risk": "高",
                "duration": 5400,
                "min_level": 7,
                "fatigue_cooldown": 900,
                "base_exp_per_min": 65,
                "base_gold_per_min": 18,
                "level_bonus_exp": 24,
                "level_bonus_gold": 7,
                "completion_bonus": {"exp": 800, "gold": 260},
                "event_weights": {"safe": 20, "standard": 40, "risky": 30, "disaster": 10},
                "drop_tier": "mid",
                "bounty_tag": "adventure_hunt",
                "bounty_progress": 2,
            },
            {
                "key": "peril",
                "name": "九死一生",
                "aliases": ["绝境", "险行", "九死一生", "peril"],
                "description": "闯入危险禁地探寻机缘，风险极高，但收获也最惊人。",
                "risk": "极高",
                "duration": 7200,
                "min_level": 12,
                "fatigue_cooldown": 1200,
                "base_exp_per_min": 80,
                "base_gold_per_min": 22,
                "level_bonus_exp": 30,
                "level_bonus_gold": 9,
                "completion_bonus": {"exp": 1200, "gold": 320},
                "event_weights": {"safe": 10, "standard": 30, "risky": 35, "disaster": 25},
                "drop_tier": "high",
                "bounty_tag": "adventure_peril",
                "bounty_progress": 3,
            },
        ],
        "event_groups": {
            "safe": [
                {
                    "key": "herb_bloom",
                    "name": "灵药丰收",
                    "desc": "你偶遇灵药生长之地，顺手收获了一些机缘。",
                    "exp_mult": 1.15,
                    "gold_mult": 1.1,
                    "item_chance": 80,
                    "bonus_progress": 0,
                },
                {
                    "key": "travel_insight",
                    "name": "旅途悟道",
                    "desc": "山河风物触动心神，你对修行的理解更深了一分。",
                    "exp_mult": 1.25,
                    "gold_mult": 1.0,
                    "item_chance": 60,
                    "bonus_progress": 0,
                },
                {
                    "key": "ally_help",
                    "name": "前辈相助",
                    "desc": "偶遇前辈指点并赐下些许资粮，令你受益良多。",
                    "exp_mult": 1.1,
                    "gold_mult": 1.35,
                    "item_chance": 40,
                    "bonus_progress": 0,
                },
            ],
            "standard": [
                {
                    "key": "steady_path",
                    "name": "平稳推进",
                    "desc": "此行波澜不惊，你稳稳完成了既定目标。",
                    "exp_mult": 1.0,
                    "gold_mult": 1.0,
                    "item_chance": 35,
                    "bonus_progress": 0,
                },
                {
                    "key": "beast_skirmish",
                    "name": "遭遇拦路妖兽",
                    "desc": "你击退了挡路妖兽，增长了不少实战经验。",
                    "exp_mult": 1.2,
                    "gold_mult": 1.25,
                    "item_chance": 55,
                    "bonus_progress": 1,
                },
                {
                    "key": "secret_cache",
                    "name": "秘宝遗迹",
                    "desc": "你发现一处残破遗迹，顺手带回了一些物资。",
                    "exp_mult": 1.05,
                    "gold_mult": 1.4,
                    "item_chance": 65,
                    "bonus_progress": 0,
                },
            ],
            "risky": [
                {
                    "key": "blood_battle",
                    "name": "血战妖巢",
                    "desc": "你深入妖巢奋战到底，凶险却收获丰厚。",
                    "exp_mult": 1.45,
                    "gold_mult": 1.35,
                    "item_chance": 85,
                    "bonus_progress": 2,
                },
                {
                    "key": "ancient_trial",
                    "name": "远古试炼",
                    "desc": "古老禁制骤然开启，你历经考验，收获不小。",
                    "exp_mult": 1.6,
                    "gold_mult": 1.1,
                    "item_chance": 50,
                    "bonus_progress": 1,
                },
                {
                    "key": "trade_windfall",
                    "name": "天降横财",
                    "desc": "你救下商队，获得了一笔意外酬谢。",
                    "exp_mult": 0.9,
                    "gold_mult": 1.8,
                    "item_chance": 55,
                    "bonus_progress": 0,
                },
            ],
            "disaster": [
                {
                    "key": "ambush_fail",
                    "name": "埋伏受创",
                    "desc": "你遭遇伏击，被迫撤退休整，所幸保住了性命。",
                    "exp_mult": 0.55,
                    "gold_mult": 0.5,
                    "item_chance": 15,
                    "bonus_progress": 0,
                    "injury": True,
                },
                {
                    "key": "lost_in_fog",
                    "name": "迷失古雾",
                    "desc": "你陷入迷雾耽误了大量时间，只能仓促返回。",
                    "exp_mult": 0.6,
                    "gold_mult": 0.4,
                    "item_chance": 20,
                    "bonus_progress": 0,
                },
            ],
        },
        "drop_tables": {
            "low": [
                {"name": "灵草", "weight": 50, "min": 1, "max": 3},
                {"name": "精铁", "weight": 30, "min": 1, "max": 2},
                {"name": "灵石碎片", "weight": 20, "min": 2, "max": 5},
            ],
            "mid": [
                {"name": "灵草", "weight": 35, "min": 2, "max": 5},
                {"name": "玄铁", "weight": 25, "min": 1, "max": 3},
                {"name": "灵兽毛皮", "weight": 20, "min": 1, "max": 3},
                {"name": "星陨石", "weight": 20, "min": 1, "max": 2},
            ],
            "high": [
                {"name": "玄铁", "weight": 30, "min": 2, "max": 4},
                {"name": "星陨石", "weight": 25, "min": 1, "max": 2},
                {"name": "灵兽内丹", "weight": 20, "min": 1, "max": 1},
                {"name": "功法残页", "weight": 15, "min": 1, "max": 1},
                {"name": "天材地宝", "weight": 10, "min": 1, "max": 1},
            ],
        },
    }

    def __init__(self, db: DataBase, storage_ring_manager: "StorageRingManager" = None):
        self.db = db
        self.storage_ring_manager = storage_ring_manager
        self.routes: Dict[str, dict] = {}
        self.route_alias_index: Dict[str, str] = {}
        self.event_groups: Dict[str, List[dict]] = {}
        self.drop_tables: Dict[str, List[dict]] = {}
        self.default_route_key = "scout"
        self.reload_config()

    def reload_config(self):
        """重新加载历练配置。"""
        config = self._load_config_file()
        routes = config.get("routes") or self.DEFAULT_CONFIG["routes"]
        self.routes = {route["key"]: route for route in routes}
        self.default_route_key = next(iter(self.routes.keys()), "scout")

        self.route_alias_index = {}
        for key, route in self.routes.items():
            aliases = set(route.get("aliases", []))
            aliases.add(route["key"])
            aliases.add(route["name"])
            if key == "scout":
                aliases.update({"short", "短途"})
            elif key == "journey":
                aliases.update({"medium", "中途"})
            elif key == "hunt":
                aliases.update({"long", "长途"})
            elif key == "peril":
                aliases.update({"绝境", "险行"})
            for alias in aliases:
                if alias:
                    self.route_alias_index[str(alias).strip().lower()] = key

        self.event_groups = config.get("event_groups") or self.DEFAULT_CONFIG["event_groups"]
        self.drop_tables = config.get("drop_tables") or self.DEFAULT_CONFIG["drop_tables"]

    def _load_config_file(self) -> dict:
        """加载配置文件，失败时回退到默认配置。"""
        if self.CONFIG_FILE.exists():
            try:
                with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                logger.info("已加载 adventure_config.json")
                return data
            except Exception as exc:
                logger.error(f"加载 adventure_config.json 失败，将使用默认配置: {exc}")
        return self.DEFAULT_CONFIG

    def get_route_overview(self) -> List[dict]:
        """返回历练路线总览。"""
        return [
            {
                "key": route["key"],
                "name": route["name"],
                "risk": route.get("risk", "未知"),
                "duration": route.get("duration", 0),
                "min_level": route.get("min_level", 0),
                "description": route.get("description", ""),
            }
            for route in self.routes.values()
        ]

    async def start_adventure(self, user_id: str, route_token: str = "") -> Tuple[bool, str]:
        """开始指定路线的历练。"""
        player = await self.db.get_player_by_id(user_id)
        if not player:
            return False, "❌ 你还未踏入修仙之路！"

        user_cd = await self.db.ext.get_user_cd(user_id)
        if not user_cd:
            await self.db.ext.create_user_cd(user_id)
            user_cd = await self.db.ext.get_user_cd(user_id)

        if user_cd.type != UserStatus.IDLE:
            return False, f"❌ 你当前正{UserStatus.get_name(user_cd.type)}，无法开始历练！"

        route_key = self._resolve_route(route_token)
        route = self.routes.get(route_key)
        if not route:
            return False, "❌ 未找到对应的历练路线，请先发送 /历练信息 查看可选路线。"

        if player.level_index < route.get("min_level", 0):
            return False, "❌ 你的境界还不足以踏上这条路线，先提升境界吧！"

        cooldown_end = self._get_route_cooldown_end(user_cd, route_key)
        now = int(time.time())
        if cooldown_end > now:
            remaining = cooldown_end - now
            minutes = max(1, remaining // 60)
            return False, f"⏳ 该路线尚在休整中，请 {minutes} 分钟后再试。"

        duration = route.get("duration", 3600)
        scheduled_time = now + duration
        await self.db.ext.set_user_busy(
            user_id,
            UserStatus.ADVENTURING,
            scheduled_time,
            extra_data={"route_key": route_key},
        )

        fatigue = route.get("fatigue_cooldown", 0)
        hint = [
            f"✅ 你选择了【{route['name']}】——{route.get('description', '未知冒险')}",
            f"路线风险：{route.get('risk', '未知')} | 历练时长：{duration // 60} 分钟",
        ]
        if route.get("min_level", 0):
            hint.append(f"推荐境界：≥ {route['min_level']}")
        if fatigue:
            hint.append(f"该路线完成后需要休整 {fatigue // 60} 分钟。")
        return True, "\n".join(hint)

    async def finish_adventure(self, user_id: str) -> Tuple[bool, str, Optional[Dict]]:
        """结算历练奖励。"""
        player = await self.db.get_player_by_id(user_id)
        if not player:
            return False, "❌ 你还未踏入修仙之路！", None

        user_cd = await self.db.ext.get_user_cd(user_id)
        if not user_cd or user_cd.type != UserStatus.ADVENTURING:
            return False, "❌ 你当前不在历练中。", None

        now = int(time.time())
        if now < user_cd.scheduled_time:
            remaining = user_cd.scheduled_time - now
            minutes = remaining // 60
            seconds = remaining % 60
            return False, f"❌ 历练尚未完成！还需 {minutes}分{seconds}秒。", None

        extra = self._get_extra_data(user_cd)
        route_token = str(extra.get("route_key", self.default_route_key) or self.default_route_key)
        route_key = self._resolve_route(route_token)
        route = self.routes.get(route_key) or self.routes.get(self.default_route_key)
        if not route:
            return False, "❌ 未找到历练路线配置，请联系管理员。", None

        if route_token != route_key:
            extra["route_key"] = route_key
            user_cd.set_extra_data(extra)
            await self.db.ext.update_user_cd(user_cd)

        adventure_duration = now - user_cd.create_time
        scheduled_duration = max(1, user_cd.scheduled_time - user_cd.create_time)
        effective_duration = min(adventure_duration, scheduled_duration)
        event = self._trigger_route_event(route)

        rewards = self._calculate_rewards(player, route, effective_duration, event)
        dropped_items, item_msg = await self._handle_drops(player, route, event)

        player.experience += rewards["exp"]
        player.gold += rewards["gold"]
        await self.db.update_player(player)

        fatigue = route.get("fatigue_cooldown", 0)
        if event.get("injury"):
            fatigue += 600
        if fatigue:
            await self._set_route_cooldown(user_cd, route["key"], int(time.time()) + fatigue)

        await self.db.ext.set_user_free(user_id)

        fatigue_hint = f"\n⏳ 该路线休整：{fatigue // 60} 分钟" if fatigue else ""
        display_minutes = effective_duration // 60
        msg = (
            f"🎒 历练归来 · {route['name']}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"{event['desc']}\n\n"
            f"本次历练：{display_minutes} 分钟\n"
            f"获得修为：{rewards['exp']:,}\n"
            f"获得灵石：{rewards['gold']:,}"
            f"{item_msg}"
            f"\n━━━━━━━━━━━━━━━\n"
            f"当前修为：{player.experience:,}\n"
            f"当前灵石：{player.gold:,}"
            f"{fatigue_hint}"
        )

        reward_data = {
            "route_key": route["key"],
            "route_name": route["name"],
            "event_key": event.get("key"),
            "event_desc": event["desc"],
            "exp_reward": rewards["exp"],
            "gold_reward": rewards["gold"],
            "items": dropped_items,
            "duration": effective_duration,
            "bounty_tag": route.get("bounty_tag", "adventure"),
            "bounty_progress": max(1, route.get("bounty_progress", 1) + event.get("bonus_progress", 0)),
        }
        return True, msg, reward_data

    async def check_adventure_status(self, user_id: str) -> Tuple[bool, str]:
        """查看当前历练状态。"""
        user_cd = await self.db.ext.get_user_cd(user_id)
        if not user_cd or user_cd.type != UserStatus.ADVENTURING:
            return False, "❌ 你当前不在历练中。"

        now = int(time.time())
        route_name = "未知路线"
        extra = self._get_extra_data(user_cd)
        route_token = str(extra.get("route_key", self.default_route_key) or self.default_route_key)
        route_key = self._resolve_route(route_token)
        route = self.routes.get(route_key)
        if route:
            route_name = route["name"]
            if route_token != route_key:
                extra["route_key"] = route_key
                user_cd.set_extra_data(extra)
                await self.db.ext.update_user_cd(user_cd)

        if now >= user_cd.scheduled_time:
            return True, f"✅ {route_name} 已完成！使用 /完成历练 领取奖励。"

        remaining = user_cd.scheduled_time - now
        elapsed = now - user_cd.create_time
        minutes = remaining // 60
        seconds = remaining % 60
        elapsed_minutes = elapsed // 60

        msg = (
            f"📍 历练进度 · {route_name}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"已历练：{elapsed_minutes} 分钟\n"
            f"剩余时间：{minutes}分{seconds}秒\n"
            f"请耐心等待历练完成..."
        )
        return True, msg

    def _get_extra_data(self, user_cd: Optional[UserCd]) -> Dict[str, Any]:
        if not user_cd:
            return {}
        if hasattr(user_cd, "get_extra_data"):
            return user_cd.get_extra_data()
        return {}

    def _get_route_cooldown_end(self, user_cd: Optional[UserCd], route_key: str) -> int:
        extra_data = self._get_extra_data(user_cd)
        route_cooldowns = extra_data.get(ADVENTURE_ROUTE_COOLDOWNS_KEY, {})
        if not isinstance(route_cooldowns, dict):
            return 0
        return int(route_cooldowns.get(route_key, 0) or 0)

    async def _set_route_cooldown(self, user_cd: UserCd, route_key: str, cooldown_end: int):
        extra_data = self._get_extra_data(user_cd)
        route_cooldowns = extra_data.get(ADVENTURE_ROUTE_COOLDOWNS_KEY, {})
        if not isinstance(route_cooldowns, dict):
            route_cooldowns = {}
        route_cooldowns[route_key] = int(cooldown_end)
        extra_data[ADVENTURE_ROUTE_COOLDOWNS_KEY] = route_cooldowns
        user_cd.set_extra_data(extra_data)
        await self.db.ext.update_user_cd(user_cd)

    def _resolve_route(self, token: str) -> str:
        if not token:
            return self.default_route_key
        normalized = str(token).strip().lower()
        return self.route_alias_index.get(normalized, self.default_route_key)

    def _trigger_route_event(self, route: dict) -> dict:
        weights = route.get("event_weights", {})
        if not weights:
            group_key = "standard"
        else:
            total_weight = sum(max(0, weight) for weight in weights.values()) or 1
            roll = random.randint(1, total_weight)
            upto = 0
            group_key = "standard"
            for key, weight in weights.items():
                upto += max(0, weight)
                if roll <= upto:
                    group_key = key
                    break

        group = self.event_groups.get(group_key) or self.event_groups.get("standard") or self.DEFAULT_CONFIG["event_groups"]["standard"]
        return random.choice(group)

    def _calculate_rewards(self, player: Player, route: dict, duration: int, event: dict) -> Dict[str, int]:
        duration_minutes = max(1, duration // 60)
        base_exp = duration_minutes * route.get("base_exp_per_min", 40)
        base_gold = duration_minutes * route.get("base_gold_per_min", 10)

        level_bonus_exp = player.level_index * route.get("level_bonus_exp", 10)
        level_bonus_gold = player.level_index * route.get("level_bonus_gold", 2)

        completion_bonus = route.get("completion_bonus", {})
        exp_total = base_exp + level_bonus_exp + completion_bonus.get("exp", 0)
        gold_total = base_gold + level_bonus_gold + completion_bonus.get("gold", 0)

        final_exp = max(0, int(exp_total * event.get("exp_mult", 1.0)))
        final_gold = max(0, int(gold_total * event.get("gold_mult", 1.0)))
        return {"exp": final_exp, "gold": final_gold}

    async def _handle_drops(self, player: Player, route: dict, event: dict) -> Tuple[List[Tuple[str, int]], str]:
        dropped_items: List[Tuple[str, int]] = []
        if not self.storage_ring_manager:
            return dropped_items, ""

        item_chance = event.get("item_chance", 40)
        if random.randint(1, 100) > item_chance:
            return dropped_items, ""

        tier = event.get("drop_tier") or route.get("drop_tier") or "low"
        drop_table = self.drop_tables.get(tier, self.DEFAULT_CONFIG["drop_tables"]["low"])
        total_weight = sum(item["weight"] for item in drop_table)
        roll = random.randint(1, total_weight)
        upto = 0
        chosen = drop_table[0]
        for item in drop_table:
            upto += item["weight"]
            if roll <= upto:
                chosen = item
                break

        count = random.randint(chosen["min"], chosen["max"])
        dropped_items.append((chosen["name"], count))

        item_lines = []
        for item_name, qty in dropped_items:
            success, _ = await self.storage_ring_manager.store_item(player, item_name, qty, silent=True)
            if success:
                item_lines.append(f"  · {item_name} x{qty}")
            else:
                item_lines.append(f"  · {item_name} x{qty}（储物戒已满，已丢失）")

        if item_lines:
            return dropped_items, "\n\n📦 获得物品：\n" + "\n".join(item_lines)
        return dropped_items, ""
