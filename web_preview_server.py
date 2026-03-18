import argparse
import json
import os
import sqlite3
import time
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from battle_hp_utils import resolve_boss_battle_hp_state

ROOT_DIR = Path(__file__).resolve().parent
WEB_DIR = ROOT_DIR / "webui"
CONFIG_DIR = ROOT_DIR / "config"
SECT_POSITIONS = {
    0: "\u5b97\u4e3b",
    1: "\u526f\u5b97\u4e3b",
    2: "\u957f\u8001",
    3: "\u4eb2\u4f20\u5f1f\u5b50",
    4: "\u5916\u95e8\u5f1f\u5b50",
}
NORMAL_LOAN_CAPS = [
    (0, 9, 10_000),
    (10, 12, 30_000),
    (13, 15, 80_000),
    (16, 18, 150_000),
    (19, 21, 300_000),
    (22, 24, 600_000),
    (25, 35, 1_000_000),
]
BREAKTHROUGH_LOAN_BUFFER = 1.3

SPIRIT_FARM_HERBS = {
    "灵草": {"grow_time": 3600, "exp_yield": 500, "gold_yield": 100, "wither_time": 172800},
    "血灵草": {"grow_time": 7200, "exp_yield": 1500, "gold_yield": 300, "wither_time": 172800},
    "冰心草": {"grow_time": 14400, "exp_yield": 4000, "gold_yield": 800, "wither_time": 172800},
    "火焰花": {"grow_time": 28800, "exp_yield": 10000, "gold_yield": 2000, "wither_time": 172800},
    "九叶灵芝": {"grow_time": 86400, "exp_yield": 30000, "gold_yield": 6000, "wither_time": 172800},
}
FARM_LEVELS = {
    1: {"slots": 3, "upgrade_cost": 5000},
    2: {"slots": 5, "upgrade_cost": 15000},
    3: {"slots": 8, "upgrade_cost": 50000},
    4: {"slots": 12, "upgrade_cost": 150000},
    5: {"slots": 20, "upgrade_cost": 0},
}


def load_json_file(path: Path, default: Any):
    try:
        with path.open("r", encoding="utf-8") as fp:
            return json.load(fp)
    except Exception:
        return default

def load_web_server_config() -> dict[str, Any]:
    config = load_json_file(CONFIG_DIR / "game_config.json", {})
    web_config = config.get("web_server", {}) if isinstance(config, dict) else {}

    host = str(web_config.get("host", "0.0.0.0") or "0.0.0.0")
    try:
        port = int(web_config.get("port", 8765) or 8765)
    except (TypeError, ValueError):
        port = 8765

    return {
        "host": host,
        "port": port,
    }


def detect_default_db() -> Path | None:
    candidates = [
        ROOT_DIR / "xiuxian_data_lite.db",
        ROOT_DIR / "xiuxian_data_v2.db",
    ]

    appdata = os.getenv("APPDATA")
    if appdata:
        plugin_dir = Path(appdata) / "AstrBot" / "data" / "astrbot_plugin_monixiuxian2"
        candidates.extend(
            [
                plugin_dir / "xiuxian_data_v2.db",
                plugin_dir / "xiuxian_data_lite.db",
            ]
        )

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


class WebPreviewRepository:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.level_names = load_json_file(CONFIG_DIR / "level_config.json", [])
        self.body_level_names = load_json_file(CONFIG_DIR / "body_level_config.json", [])
        self.items_config = load_json_file(CONFIG_DIR / "items.json", {})
        self.weapons_config = load_json_file(CONFIG_DIR / "weapons.json", [])
        self.pills_config = load_json_file(CONFIG_DIR / "pills.json", [])
        self.exp_pills_config = load_json_file(CONFIG_DIR / "exp_pills.json", [])
        self.utility_pills_config = load_json_file(CONFIG_DIR / "utility_pills.json", [])
        self.adventure_config = load_json_file(CONFIG_DIR / "adventure_config.json", {"routes": []})
        self.bounty_config = load_json_file(CONFIG_DIR / "bounty_templates.json", {"difficulties": {}, "templates": [], "item_tables": {}})
        self._item_index = self._build_item_index()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _build_item_index(self) -> dict[str, dict[str, Any]]:
        index: dict[str, dict[str, Any]] = {}

        def add_items(source: Any, fallback_type: str | None = None):
            if isinstance(source, dict):
                values = source.values()
            elif isinstance(source, list):
                values = source
            else:
                values = []

            for item in values:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip()
                if not name:
                    continue
                index[name] = {
                    "type": str(item.get("type") or fallback_type or "other"),
                    "rank": str(item.get("rank", "未知")),
                    "description": str(item.get("description", "")),
                    "required_level_index": int(item.get("required_level_index", 0) or 0),
                }

        add_items(self.items_config)
        add_items(self.weapons_config, "weapon")
        add_items(self.pills_config, "pill")
        add_items(self.exp_pills_config, "exp_pill")
        add_items(self.utility_pills_config, "utility_pill")
        return index

    def _item_meta(self, item_name: str) -> dict[str, Any]:
        meta = self._item_index.get(item_name, {})
        return {
            "type": meta.get("type", "other"),
            "rank": meta.get("rank", "未知"),
            "description": meta.get("description", ""),
            "required_level_index": int(meta.get("required_level_index", 0) or 0),
        }

    def _level_name(self, cultivation_type: str, level_index: int) -> str:
        levels = self.body_level_names if cultivation_type == "体修" else self.level_names
        if 0 <= level_index < len(levels):
            return str(levels[level_index].get("level_name", f"境界{level_index}"))
        return f"境界{level_index}"

    @staticmethod
    def _safe_json(text: str, default: Any):
        try:
            return json.loads(text) if text else default
        except Exception:
            return default

    @staticmethod
    def _display_name(row: sqlite3.Row) -> str:
        return row["user_name"] or row["user_id"]

    @staticmethod
    def _power_score(row: sqlite3.Row) -> int:
        return (
            int(row["physical_damage"] or 0)
            + int(row["magic_damage"] or 0)
            + int(row["physical_defense"] or 0)
            + int(row["magic_defense"] or 0)
            + int(row["mental_power"] or 0) // 10
        )

    def _table_exists(self, conn: sqlite3.Connection, table_name: str) -> bool:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
            (table_name,),
        ).fetchone()
        return row is not None

    @staticmethod
    def _resolve_boss_battle_hp_for_display(player_row: sqlite3.Row, user_cd_row: sqlite3.Row | None) -> tuple[int, int, bool, int]:
        experience = int(player_row["experience"] or 0)
        max_hp = max(1, experience // 2)
        current_hp = int(player_row["hp"] or 0)

        if not user_cd_row:
            return (max(1, current_hp) if current_hp > 0 else max_hp, max_hp, False, 0)

        resolved_hp, recovery_enabled, cooldown_remaining, _, _ = resolve_boss_battle_hp_state(
            current_hp,
            max_hp,
            WebPreviewRepository._safe_json(user_cd_row["extra_data"], {}),
            now=int(time.time()),
        )
        return resolved_hp, max_hp, recovery_enabled, cooldown_remaining

    def _bank_realm_loan_cap(self, level_index: int) -> int:
        for min_level, max_level, cap in NORMAL_LOAN_CAPS:
            if min_level <= level_index <= max_level:
                return cap
        return NORMAL_LOAN_CAPS[-1][2]

    def _breakthrough_pill_price(self, level_index: int) -> int | None:
        if isinstance(self.pills_config, dict):
            values = self.pills_config.values()
        elif isinstance(self.pills_config, list):
            values = self.pills_config
        else:
            values = []

        prices = []
        for item in values:
            if not isinstance(item, dict):
                continue
            if str(item.get("subtype", "")) != "breakthrough":
                continue
            if int(item.get("required_level_index", -1) or -1) != level_index:
                continue
            price = int(item.get("price", 0) or 0)
            if price > 0:
                prices.append(price)
        return max(prices) if prices else None

    def get_players(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT user_id, user_name, level_index, cultivation_type, experience, gold
                FROM players
                ORDER BY experience DESC, gold DESC, user_id ASC
                """
            ).fetchall()

        return [
            {
                "user_id": row["user_id"],
                "name": self._display_name(row),
                "level_name": self._level_name(row["cultivation_type"], int(row["level_index"] or 0)),
                "cultivation_type": row["cultivation_type"],
            }
            for row in rows
        ]

    def get_world_summary(self) -> dict[str, Any]:
        with self._connect() as conn:
            player_count = conn.execute("SELECT COUNT(*) AS c FROM players").fetchone()["c"]
            sect_count = 0
            if self._table_exists(conn, "sects"):
                sect_count = conn.execute("SELECT COUNT(*) AS c FROM sects").fetchone()["c"]
            rift_count = 0
            if self._table_exists(conn, "rifts"):
                rift_count = conn.execute("SELECT COUNT(*) AS c FROM rifts").fetchone()["c"]

        return {
            "player_count": player_count,
            "sect_count": sect_count,
            "rift_count": rift_count,
        }

    def get_dashboard(self, user_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            player = conn.execute("SELECT * FROM players WHERE user_id = ?", (user_id,)).fetchone()
            if not player:
                raise KeyError(user_id)

            sect_name = "无宗门"
            if self._table_exists(conn, "sects") and int(player["sect_id"] or 0) > 0:
                sect = conn.execute(
                    "SELECT sect_name FROM sects WHERE sect_id = ?",
                    (player["sect_id"],),
                ).fetchone()
                if sect:
                    sect_name = sect["sect_name"]

            ranking_rows = conn.execute(
                """
                SELECT user_id, user_name, level_index, cultivation_type, experience, gold,
                       physical_damage, magic_damage, physical_defense, magic_defense, mental_power
                FROM players
                """
            ).fetchall()

        players = list(ranking_rows)
        level_sorted = sorted(players, key=lambda row: (int(row["experience"] or 0), int(row["gold"] or 0)), reverse=True)
        wealth_sorted = sorted(players, key=lambda row: int(row["gold"] or 0), reverse=True)
        power_sorted = sorted(players, key=self._power_score, reverse=True)

        def build_ranking(rows: list[sqlite3.Row], value_getter):
            result = []
            for index, row in enumerate(rows[:8], start=1):
                result.append(
                    {
                        "rank": index,
                        "name": self._display_name(row),
                        "level_name": self._level_name(row["cultivation_type"], int(row["level_index"] or 0)),
                        "value": value_getter(row),
                        "user_id": row["user_id"],
                    }
                )
            return result

        storage_items = self._safe_json(player["storage_ring_items"], {})
        pills_inventory = self._safe_json(player["pills_inventory"], {})
        techniques = self._safe_json(player["techniques"], [])

        def total_count(mapping: dict[str, Any]) -> int:
            total = 0
            for value in mapping.values():
                if isinstance(value, dict):
                    total += int(value.get("count", 0))
                else:
                    total += int(value or 0)
            return total

        def normalize_storage_items(items: dict[str, Any]) -> list[dict[str, Any]]:
            normalized = []
            for name, value in items.items():
                if isinstance(value, dict):
                    count = int(value.get("count", 0))
                    bound = bool(value.get("bound", False))
                else:
                    count = int(value or 0)
                    bound = False
                normalized.append({"name": name, "count": count, "bound": bound})
            normalized.sort(key=lambda item: (-item["count"], item["name"]))
            return normalized

        storage_list = normalize_storage_items(storage_items)
        user_cd = None
        with self._connect() as conn:
            if self._table_exists(conn, "user_cd"):
                user_cd = conn.execute(
                    "SELECT extra_data FROM user_cd WHERE user_id = ?",
                    (user_id,),
                ).fetchone()
        battle_hp, battle_hp_max, hp_recovering, boss_cooldown_remaining = self._resolve_boss_battle_hp_for_display(player, user_cd)

        return {
            "player": {
                "user_id": player["user_id"],
                "name": self._display_name(player),
                "cultivation_type": player["cultivation_type"],
                "level_name": self._level_name(player["cultivation_type"], int(player["level_index"] or 0)),
                "spiritual_root": player["spiritual_root"],
                "state": player["state"],
                "experience": int(player["experience"] or 0),
                "gold": int(player["gold"] or 0),
                "lifespan": int(player["lifespan"] or 0),
                "level_up_rate": int(player["level_up_rate"] or 0),
                "mental_power": int(player["mental_power"] or 0),
                "hp": int(player["hp"] or 0),
                "mp": int(player["mp"] or 0),
                "battle_hp": battle_hp,
                "battle_hp_max": battle_hp_max,
                "boss_cooldown_remaining": boss_cooldown_remaining,
                "boss_hp_recovering": hp_recovering,
                "blood_qi": int(player["blood_qi"] or 0),
                "max_blood_qi": int(player["max_blood_qi"] or 0),
                "spiritual_qi": int(player["spiritual_qi"] or 0),
                "max_spiritual_qi": int(player["max_spiritual_qi"] or 0),
                "physical_damage": int(player["physical_damage"] or 0),
                "magic_damage": int(player["magic_damage"] or 0),
                "physical_defense": int(player["physical_defense"] or 0),
                "magic_defense": int(player["magic_defense"] or 0),
                "weapon": player["weapon"] or "无",
                "armor": player["armor"] or "无",
                "main_technique": player["main_technique"] or "无",
                "storage_ring": player["storage_ring"] or "无",
                "sect_name": sect_name,
                "combat_power": self._power_score(player),
                "pill_count": total_count(pills_inventory),
                "storage_count": total_count(storage_items),
                "techniques_count": len(techniques),
            },
            "storage_ring": {
                "items": storage_list[:24],
                "used_slots": len(storage_list),
                "total_items": total_count(storage_items),
            },
            "inventory_preview": self.get_inventory_preview(storage_items, pills_inventory),
            "shop_preview": self.get_shop_preview(),
            "rift_preview": self.get_rift_preview(user_id),
            "boss_preview": self.get_boss_preview(user_id),
            "bank_preview": self.get_bank_preview(user_id),
            "blessed_land_preview": self.get_blessed_land_preview(user_id),
            "adventure_preview": self.get_adventure_preview(user_id),
            "spirit_farm_preview": self.get_spirit_farm_preview(user_id),
            "spirit_eye_preview": self.get_spirit_eye_preview(user_id),
            "dual_cultivation_preview": self.get_dual_cultivation_preview(user_id),
            "sect_preview": self.get_sect_preview(user_id),
            "bounty_preview": self.get_bounty_preview(user_id),
            "rankings": {
                "level": build_ranking(level_sorted, lambda row: int(row["experience"] or 0)),
                "wealth": build_ranking(wealth_sorted, lambda row: int(row["gold"] or 0)),
                "power": build_ranking(power_sorted, self._power_score),
            },
        }

    def get_shop_preview(self) -> dict[str, list[dict[str, Any]]]:
        def normalize_config_items(source: Any, fallback_type: str | None = None) -> list[dict[str, Any]]:
            if isinstance(source, dict):
                values = list(source.values())
            elif isinstance(source, list):
                values = source
            else:
                values = []

            result = []
            for item in values:
                if not isinstance(item, dict):
                    continue
                result.append(
                    {
                        "name": str(item.get("name", "未知物品")),
                        "type": str(item.get("type") or fallback_type or ""),
                        "rank": str(item.get("rank", "未知")),
                        "price": int(item.get("price", 0) or 0),
                        "required_level_index": int(item.get("required_level_index", 0) or 0),
                        "description": str(item.get("description", "")),
                    }
                )
            return result

        pills = []
        pills.extend(normalize_config_items(self.pills_config, "pill"))
        pills.extend(normalize_config_items(self.exp_pills_config, "exp_pill"))
        pills.extend(normalize_config_items(self.utility_pills_config, "utility_pill"))

        equipment = normalize_config_items(self.weapons_config, "weapon")
        treasure = normalize_config_items(self.items_config)

        def sort_items(items: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
            items.sort(key=lambda item: (item["price"], item["required_level_index"], item["name"]))
            return items[:limit]

        return {
            "pill": sort_items(pills),
            "weapon": sort_items([item for item in equipment if item["type"] in {"weapon", "armor", "accessory"}]),
            "treasure": sort_items(
                [
                    item
                    for item in treasure
                    if item["type"] in {"material", "main_technique", "technique", "legacy_pill", "功法", "丹药"}
                ]
            ),
        }

    def get_rift_preview(self, user_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            if not self._table_exists(conn, "rifts"):
                return {
                    "open": [],
                    "closed": [],
                    "next_refresh_in_minutes": 0,
                    "player_status": None,
                }

            rifts = conn.execute(
                "SELECT rift_id, rift_name, rift_level, required_level, rewards FROM rifts ORDER BY rift_level ASC, rift_id ASC"
            ).fetchall()

            open_ids_raw = None
            next_refresh_raw = None
            if self._table_exists(conn, "system_config"):
                open_ids_row = conn.execute(
                    "SELECT value FROM system_config WHERE key = 'rift_open_ids'"
                ).fetchone()
                next_refresh_row = conn.execute(
                    "SELECT value FROM system_config WHERE key = 'rift_open_next_refresh'"
                ).fetchone()
                open_ids_raw = open_ids_row["value"] if open_ids_row else None
                next_refresh_raw = next_refresh_row["value"] if next_refresh_row else None

            player_cd = None
            if self._table_exists(conn, "user_cd"):
                player_cd = conn.execute(
                    "SELECT type, scheduled_time, extra_data FROM user_cd WHERE user_id = ?",
                    (user_id,),
                ).fetchone()

        open_ids = set()
        if open_ids_raw:
            try:
                open_ids = {int(item) for item in json.loads(open_ids_raw)}
            except Exception:
                open_ids = set()

        # 青云秘境常驻开放
        open_ids.add(1)

        def normalize_rift(row: sqlite3.Row) -> dict[str, Any]:
            rewards = self._safe_json(row["rewards"], {})
            exp_range = rewards.get("exp", [0, 0])
            gold_range = rewards.get("gold", [0, 0])
            return {
                "rift_id": int(row["rift_id"]),
                "name": row["rift_name"],
                "rift_level": int(row["rift_level"]),
                "required_level": int(row["required_level"]),
                "required_level_name": self._level_name("灵修", int(row["required_level"] or 0)),
                "exp_range": exp_range,
                "gold_range": gold_range,
            }

        open_rifts = []
        closed_rifts = []
        for row in rifts:
            target = open_rifts if int(row["rift_id"]) in open_ids else closed_rifts
            target.append(normalize_rift(row))

        next_refresh_in_minutes = 0
        if next_refresh_raw:
            try:
                remaining_seconds = max(0, int(next_refresh_raw) - int(__import__("time").time()))
                next_refresh_in_minutes = remaining_seconds // 60
            except Exception:
                next_refresh_in_minutes = 0

        player_status = None
        if player_cd and int(player_cd["type"] or 0) == 3:
            extra_data = self._safe_json(player_cd["extra_data"], {})
            player_status = {
                "is_exploring": True,
                "scheduled_time": int(player_cd["scheduled_time"] or 0),
                "rift_id": int(extra_data.get("rift_id", 0) or 0),
                "rift_level": int(extra_data.get("rift_level", 0) or 0),
            }

        return {
            "open": open_rifts,
            "closed": closed_rifts,
            "next_refresh_in_minutes": next_refresh_in_minutes,
            "player_status": player_status,
        }

    def get_boss_preview(self, user_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            active_boss = None
            recent_bosses = []
            player_status = None
            if self._table_exists(conn, "boss"):
                active_boss = conn.execute(
                    "SELECT * FROM boss WHERE status = 1 ORDER BY create_time DESC LIMIT 1"
                ).fetchone()
                recent_bosses = conn.execute(
                    "SELECT * FROM boss ORDER BY create_time DESC LIMIT 5"
                ).fetchall()

            player = conn.execute(
                "SELECT user_id, user_name, experience, hp FROM players WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            user_cd = None
            if self._table_exists(conn, "user_cd"):
                user_cd = conn.execute(
                    "SELECT extra_data FROM user_cd WHERE user_id = ?",
                    (user_id,),
                ).fetchone()

            next_spawn_raw = None
            if self._table_exists(conn, "system_config"):
                row = conn.execute(
                    "SELECT value FROM system_config WHERE key = 'boss_next_spawn_time'"
                ).fetchone()
                next_spawn_raw = row["value"] if row else None

        def normalize_boss(row: sqlite3.Row) -> dict[str, Any]:
            hp = int(row["hp"] or 0)
            max_hp = int(row["max_hp"] or 0)
            hp_percent = round((hp / max_hp) * 100, 1) if max_hp > 0 else 0.0
            return {
                "boss_id": int(row["boss_id"]),
                "name": row["boss_name"],
                "level": row["boss_level"],
                "hp": hp,
                "max_hp": max_hp,
                "hp_percent": hp_percent,
                "atk": int(row["atk"] or 0),
                "defense": int(row["defense"] or 0),
                "stone_reward": int(row["stone_reward"] or 0),
                "status": int(row["status"] or 0),
                "create_time": int(row["create_time"] or 0),
                "is_enrage_range": hp_percent <= 30.0,
            }

        if player:
            battle_hp, battle_hp_max, hp_recovering, cooldown_remaining = self._resolve_boss_battle_hp_for_display(player, user_cd)
            player_status = {
                "name": player["user_name"] or player["user_id"],
                "battle_hp": battle_hp,
                "battle_hp_max": battle_hp_max,
                "battle_hp_percent": round((battle_hp / battle_hp_max) * 100, 1) if battle_hp_max > 0 else 0.0,
                "cooldown_remaining_minutes": cooldown_remaining // 60,
                "cooldown_remaining_seconds": cooldown_remaining % 60,
                "cooldown_remaining": cooldown_remaining,
                "hp_recovering": hp_recovering,
                "recovery_desc": "每分钟恢复10%，约10分钟恢复满血" if hp_recovering else "当前战斗HP已恢复完成",
                "can_challenge": cooldown_remaining <= 0,
            }

        next_spawn_in_minutes = 0
        if next_spawn_raw:
            try:
                remaining_seconds = max(0, int(next_spawn_raw) - int(time.time()))
                next_spawn_in_minutes = remaining_seconds // 60
            except Exception:
                next_spawn_in_minutes = 0

        normalized_recent = [normalize_boss(row) for row in recent_bosses]
        return {
            "active": normalize_boss(active_boss) if active_boss else None,
            "recent": normalized_recent,
            "next_spawn_in_minutes": next_spawn_in_minutes,
            "enrage_threshold_percent": 30,
            "enrage_skills": [
                {"name": "回血", "desc": "5回合内每回合在玩家出手前恢复15%-20%最大生命"},
                {"name": "暴怒", "desc": "5回合内攻击额外提升200%，即按3倍攻击结算"},
                {"name": "石化", "desc": "5回合内按90%到50%递减减伤，并反弹玩家造成的实际伤害"},
                {"name": "闪避", "desc": "5回合内拥有50%闪避概率"},
                {"name": "咆哮", "desc": "玩家3回合内因恐惧无法造成伤害，但同时拥有30%闪避"},
            ],
            "player_status": player_status,
        }

    def get_bank_preview(self, user_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            player = conn.execute(
                "SELECT user_id, user_name, gold, level_index, cultivation_type FROM players WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            bank_account = None
            loan = None
            transactions = []

            if self._table_exists(conn, "bank_accounts"):
                bank_account = conn.execute(
                    "SELECT balance, last_interest_time FROM bank_accounts WHERE user_id = ?",
                    (user_id,),
                ).fetchone()

            if self._table_exists(conn, "bank_loans"):
                loan = conn.execute(
                    """
                    SELECT id, principal, interest_rate, borrowed_at, due_at, status, loan_type
                    FROM bank_loans
                    WHERE user_id = ? AND status = 'active'
                    ORDER BY borrowed_at DESC
                    LIMIT 1
                    """,
                    (user_id,),
                ).fetchone()

            if self._table_exists(conn, "bank_transactions"):
                transactions = conn.execute(
                    """
                    SELECT trans_type, amount, balance_after, description, created_at
                    FROM bank_transactions
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    LIMIT 8
                    """,
                    (user_id,),
                ).fetchall()

        balance = int(bank_account["balance"] or 0) if bank_account else 0
        cash = int(player["gold"] or 0) if player else 0
        level_index = int(player["level_index"] or 0) if player else 0
        cultivation_type = str(player["cultivation_type"] or "灵修") if player else "灵修"
        total_assets = cash + balance
        realm_cap = self._bank_realm_loan_cap(level_index)
        normal_cap = max(1_000, min(realm_cap, max(10_000, total_assets * 3)))
        breakthrough_pill_price = self._breakthrough_pill_price(level_index)
        breakthrough_cap = int(breakthrough_pill_price * BREAKTHROUGH_LOAN_BUFFER) if breakthrough_pill_price else normal_cap
        last_interest_time = int(bank_account["last_interest_time"] or 0) if bank_account else 0
        pending_interest = 0
        if balance > 0 and last_interest_time > 0:
            days_passed = (int(time.time()) - last_interest_time) // 86400
            if days_passed >= 1:
                pending_interest = int(balance * (((1 + 0.001) ** days_passed) - 1))

        normalized_loan = None
        if loan:
            now = int(time.time())
            days_borrowed = max(1, (now - int(loan["borrowed_at"])) // 86400)
            current_interest = int(int(loan["principal"]) * float(loan["interest_rate"]) * days_borrowed)
            total_due = int(loan["principal"]) + current_interest
            normalized_loan = {
                "id": int(loan["id"]),
                "principal": int(loan["principal"]),
                "interest_rate": float(loan["interest_rate"]),
                "borrowed_at": int(loan["borrowed_at"]),
                "due_at": int(loan["due_at"]),
                "status": loan["status"],
                "loan_type": loan["loan_type"],
                "current_interest": current_interest,
                "total_due": total_due,
                "days_remaining": max(0, (int(loan["due_at"]) - now) // 86400),
                "is_overdue": now > int(loan["due_at"]),
            }

        normalized_transactions = [
            {
                "trans_type": row["trans_type"],
                "amount": int(row["amount"] or 0),
                "balance_after": int(row["balance_after"] or 0),
                "description": row["description"],
                "created_at": int(row["created_at"] or 0),
            }
            for row in transactions
        ]

        return {
            "level_name": self._level_name(cultivation_type, level_index),
            "balance": balance,
            "cash": cash,
            "total_assets": total_assets,
            "pending_interest": pending_interest,
            "realm_cap": realm_cap,
            "normal_cap": normal_cap,
            "breakthrough_cap": breakthrough_cap,
            "breakthrough_pill_price": breakthrough_pill_price,
            "loan": normalized_loan,
            "transactions": normalized_transactions,
        }

    def get_blessed_land_preview(self, user_id: str) -> dict[str, Any]:
        prices = {
            1: ("小洞天", 10_000),
            2: ("中洞天", 50_000),
            3: ("大洞天", 200_000),
            4: ("福地", 500_000),
            5: ("洞天福地", 1_000_000),
        }

        with self._connect() as conn:
            if not self._table_exists(conn, "blessed_lands"):
                return {
                    "current": None,
                    "options": [
                        {"type": land_type, "name": name, "price": price}
                        for land_type, (name, price) in prices.items()
                    ],
                    "replace_credit_rate": 0.6,
                    "empty_state": "当前数据库中还没有洞天表数据。",
                }

            row = conn.execute(
                """
                SELECT land_type, land_name, level, exp_bonus, gold_per_hour, last_collect_time
                FROM blessed_lands
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()

        return {
            "current": (
                {
                    "land_type": int(row["land_type"]),
                    "name": row["land_name"],
                    "level": int(row["level"] or 1),
                    "exp_bonus_percent": round(float(row["exp_bonus"] or 0) * 100, 1),
                    "gold_per_hour": int(row["gold_per_hour"] or 0),
                    "last_collect_time": int(row["last_collect_time"] or 0),
                }
                if row
                else None
            ),
            "options": [
                {"type": land_type, "name": name, "price": price}
                for land_type, (name, price) in prices.items()
            ],
            "replace_credit_rate": 0.6,
            "empty_state": "当前玩家还没有洞天，可通过 Bot 指令购买后再回来查看。",
        }

    def get_adventure_preview(self, user_id: str) -> dict[str, Any]:
        routes_raw = self.adventure_config.get("routes", []) if isinstance(self.adventure_config, dict) else []
        routes = []
        route_index = {}
        for route in routes_raw:
            if not isinstance(route, dict):
                continue
            key = str(route.get("key", "")).strip()
            if not key:
                continue
            normalized = {
                "key": key,
                "name": str(route.get("name", key)),
                "risk": str(route.get("risk", "\u672a\u77e5")),
                "duration_minutes": int(int(route.get("duration", 0) or 0) / 60),
                "min_level": int(route.get("min_level", 0) or 0),
                "description": str(route.get("description", "")),
                "bounty_tag": str(route.get("bounty_tag", "adventure")),
            }
            routes.append(normalized)
            route_index[key] = normalized

        active = None
        with self._connect() as conn:
            if self._table_exists(conn, "user_cd"):
                row = conn.execute(
                    "SELECT type, scheduled_time, create_time, extra_data FROM user_cd WHERE user_id = ?",
                    (user_id,),
                ).fetchone()
                if row and int(row["type"] or 0) == 2:
                    extra = self._safe_json(row["extra_data"], {})
                    route_key = str(extra.get("route_key", "")).strip()
                    route_meta = route_index.get(route_key, {"name": route_key or "\u672a\u77e5\u8def\u7ebf", "risk": "\u672a\u77e5"})
                    now = int(time.time())
                    scheduled_time = int(row["scheduled_time"] or 0)
                    create_time = int(row["create_time"] or 0)
                    remaining_seconds = max(0, scheduled_time - now)
                    elapsed_seconds = max(0, now - create_time)
                    active = {
                        "route_key": route_key,
                        "route_name": route_meta.get("name", route_key or "\u672a\u77e5\u8def\u7ebf"),
                        "risk": route_meta.get("risk", "\u672a\u77e5"),
                        "remaining_minutes": remaining_seconds // 60,
                        "elapsed_minutes": elapsed_seconds // 60,
                        "is_complete": now >= scheduled_time,
                    }

        return {
            "active": active,
            "routes": routes,
            "empty_state": "\u5f53\u524d\u6ca1\u6709\u8fdb\u884c\u4e2d\u7684\u5386\u7ec3\uff0c\u53ef\u901a\u8fc7 Bot \u6307\u4ee4 /\u5f00\u59cb\u5386\u7ec3 <\u8def\u7ebf> \u53d1\u8d77\u5386\u7ec3\u3002",
        }

    def get_spirit_farm_preview(self, user_id: str) -> dict[str, Any]:
        options = [
            {
                "name": name,
                "grow_minutes": int(config["grow_time"] / 60),
                "exp_yield": int(config["exp_yield"]),
                "gold_yield": int(config["gold_yield"]),
            }
            for name, config in SPIRIT_FARM_HERBS.items()
        ]

        with self._connect() as conn:
            if not self._table_exists(conn, "spirit_farms"):
                return {
                    "current": None,
                    "crops": [],
                    "herbs": options,
                    "empty_state": "\u5f53\u524d\u6570\u636e\u5e93\u4e2d\u8fd8\u6ca1\u6709\u7075\u7530\u8868\u6570\u636e\u3002",
                }

            row = conn.execute(
                "SELECT user_id, level, crops FROM spirit_farms WHERE user_id = ?",
                (user_id,),
            ).fetchone()

        if not row:
            return {
                "current": None,
                "crops": [],
                "herbs": options,
                "empty_state": "\u5f53\u524d\u73a9\u5bb6\u8fd8\u6ca1\u6709\u7075\u7530\uff0c\u53ef\u901a\u8fc7 Bot \u6307\u4ee4 /\u5f00\u57a6\u7075\u7530 \u540e\u518d\u56de\u6765\u67e5\u770b\u3002",
            }

        level = int(row["level"] or 1)
        level_config = FARM_LEVELS.get(level, FARM_LEVELS[1])
        crops_raw = self._safe_json(row["crops"], [])
        now = int(time.time())
        normalized_crops = []
        for crop in crops_raw if isinstance(crops_raw, list) else []:
            if not isinstance(crop, dict):
                continue
            crop_name = str(crop.get("name", "\u7075\u8349"))
            meta = SPIRIT_FARM_HERBS.get(crop_name, SPIRIT_FARM_HERBS["\u7075\u8349"])
            plant_time = int(crop.get("plant_time", 0) or 0)
            mature_time = int(crop.get("mature_time", 0) or 0)
            wither_time = int(meta.get("wither_time", 172800) or 172800)
            wither_deadline = mature_time + wither_time
            if now < mature_time:
                state = "growing"
                remaining_minutes = max(0, (mature_time - now) // 60)
                status_text = f"\u8ddd\u79bb\u6210\u719f\u8fd8\u6709 {remaining_minutes} \u5206\u949f"
            elif now < wither_deadline:
                state = "mature"
                remaining_minutes = max(0, (wither_deadline - now) // 60)
                status_text = f"\u5df2\u6210\u719f\uff0c\u8ddd\u79bb\u67af\u840e\u8fd8\u6709 {remaining_minutes} \u5206\u949f"
            else:
                state = "withered"
                status_text = "\u5df2\u67af\u840e\uff0c\u7b49\u5f85\u6536\u83b7\u65f6\u6e05\u7406"
            normalized_crops.append(
                {
                    "name": crop_name,
                    "plant_time": plant_time,
                    "mature_time": mature_time,
                    "state": state,
                    "status_text": status_text,
                    "exp_yield": int(meta["exp_yield"]),
                    "gold_yield": int(meta["gold_yield"]),
                }
            )

        next_level = level + 1
        next_upgrade_cost = 0
        next_slots = int(level_config["slots"])
        if next_level in FARM_LEVELS:
            next_upgrade_cost = int(FARM_LEVELS[level]["upgrade_cost"])
            next_slots = int(FARM_LEVELS[next_level]["slots"])

        return {
            "current": {
                "level": level,
                "slots": int(level_config["slots"]),
                "used_slots": len(normalized_crops),
                "next_upgrade_cost": next_upgrade_cost,
                "next_slots": next_slots,
                "is_max_level": level >= max(FARM_LEVELS.keys()),
            },
            "crops": normalized_crops,
            "herbs": options,
            "empty_state": "\u5f53\u524d\u73a9\u5bb6\u8fd8\u6ca1\u6709\u7075\u7530\uff0c\u53ef\u901a\u8fc7 Bot \u6307\u4ee4 /\u5f00\u57a6\u7075\u7530 \u540e\u518d\u56de\u6765\u67e5\u770b\u3002",
        }

    def get_inventory_preview(self, storage_items: dict[str, Any], pills_inventory: dict[str, Any]) -> dict[str, Any]:
        categories = {
            "equipment": [],
            "material": [],
            "technique": [],
            "other": [],
        }

        for item_name, value in storage_items.items():
            if isinstance(value, dict):
                count = int(value.get("count", 0))
                bound = bool(value.get("bound", False))
            else:
                count = int(value or 0)
                bound = False

            meta = self._item_meta(item_name)
            item = {
                "name": item_name,
                "count": count,
                "bound": bound,
                "type": meta["type"],
                "rank": meta["rank"],
                "description": meta["description"],
                "required_level_index": meta["required_level_index"],
            }

            item_type = meta["type"]
            if item_type in {"weapon", "armor", "accessory"}:
                categories["equipment"].append(item)
            elif item_type in {"material"}:
                categories["material"].append(item)
            elif item_type in {"main_technique", "technique", "功法"}:
                categories["technique"].append(item)
            else:
                categories["other"].append(item)

        pills = []
        for item_name, count in pills_inventory.items():
            meta = self._item_meta(item_name)
            pills.append(
                {
                    "name": item_name,
                    "count": int(count or 0),
                    "type": meta["type"],
                    "rank": meta["rank"],
                    "description": meta["description"],
                    "required_level_index": meta["required_level_index"],
                }
            )

        for bucket in categories.values():
            bucket.sort(key=lambda item: (-item["count"], item["name"]))
        pills.sort(key=lambda item: (-item["count"], item["name"]))

        return {
            "categories": categories,
            "pills": pills,
            "summary": {
                "equipment": len(categories["equipment"]),
                "material": len(categories["material"]),
                "technique": len(categories["technique"]),
                "other": len(categories["other"]),
                "pills": len(pills),
            },
        }


    def get_spirit_eye_preview(self, user_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            if not self._table_exists(conn, "spirit_eyes"):
                return {
                    "current": None,
                    "eyes": [],
                    "next_refresh_in_minutes": None,
                    "empty_state": "\u5f53\u524d\u6570\u636e\u5e93\u4e2d\u8fd8\u6ca1\u6709\u7075\u773c\u8868\u6570\u636e\u3002",
                }

            rows = conn.execute(
                "SELECT eye_id, eye_type, eye_name, exp_per_hour, owner_id, owner_name, claim_time, spawn_time, last_collect_time FROM spirit_eyes ORDER BY eye_id ASC"
            ).fetchall()

            next_refresh = None
            if self._table_exists(conn, "system_config"):
                refresh_row = conn.execute(
                    "SELECT value FROM system_config WHERE key = 'spirit_eye_next_spawn_time'"
                ).fetchone()
                if refresh_row and refresh_row[0]:
                    try:
                        next_refresh = max(0, (int(refresh_row[0]) - int(time.time())) // 60)
                    except (TypeError, ValueError):
                        next_refresh = None

        now = int(time.time())
        current = None
        eyes = []
        for row in rows:
            owner_id = str(row["owner_id"] or "")
            owner_name = row["owner_name"] or "\u65e0\u4e3b"
            claim_time = int(row["claim_time"] or 0)
            last_collect_time = int(row["last_collect_time"] or 0)
            collect_base = last_collect_time or claim_time or now
            pending_hours = max(0, min(24, int((now - collect_base) // 3600)))
            pending_exp = int(row["exp_per_hour"] or 0) * pending_hours
            if owner_id == user_id:
                current = {
                    "eye_id": int(row["eye_id"]),
                    "name": row["eye_name"],
                    "exp_per_hour": int(row["exp_per_hour"] or 0),
                    "pending_exp": pending_exp,
                    "claim_minutes": max(0, (now - claim_time) // 60),
                }
            eyes.append(
                {
                    "eye_id": int(row["eye_id"]),
                    "name": row["eye_name"],
                    "exp_per_hour": int(row["exp_per_hour"] or 0),
                    "owner_name": owner_name if owner_id else "\u65e0\u4e3b",
                    "is_owned": bool(owner_id),
                    "pending_exp": pending_exp,
                }
            )

        return {
            "current": current,
            "eyes": eyes,
            "next_refresh_in_minutes": next_refresh,
            "empty_state": "\u5f53\u524d\u6ca1\u6709\u53ef\u5c55\u793a\u7684\u7075\u773c\u3002",
        }

    def get_sect_preview(self, user_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            player = conn.execute(
                """
                SELECT user_id, user_name, sect_id, sect_position, sect_contribution, level_index, cultivation_type
                FROM players
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()

            if not self._table_exists(conn, "sects"):
                return {
                    "player_sect": None,
                    "rankings": [],
                    "empty_state": "\u5f53\u524d\u6570\u636e\u5e93\u4e2d\u8fd8\u6ca1\u6709\u5b97\u95e8\u8868\u6570\u636e\u3002",
                }

            sect_rows = conn.execute(
                """
                SELECT sect_id, sect_name, sect_owner, sect_scale, sect_used_stone,
                       sect_fairyland, sect_materials, mainbuff, secbuff, elixir_room_level
                FROM sects
                ORDER BY sect_scale DESC, sect_id ASC
                LIMIT 8
                """
            ).fetchall()

            owner_ids = {row["sect_owner"] for row in sect_rows}
            owners = {}
            if owner_ids:
                placeholders = ",".join(["?"] * len(owner_ids))
                owner_rows = conn.execute(
                    f"SELECT user_id, user_name FROM players WHERE user_id IN ({placeholders})",
                    tuple(owner_ids),
                ).fetchall()
                owners = {row["user_id"]: self._display_name(row) for row in owner_rows}

            member_counts = {}
            if sect_rows:
                sect_ids = tuple(int(row["sect_id"]) for row in sect_rows)
                placeholders = ",".join(["?"] * len(sect_ids))
                count_rows = conn.execute(
                    f"""
                    SELECT sect_id, COUNT(*) AS c
                    FROM players
                    WHERE sect_id IN ({placeholders})
                    GROUP BY sect_id
                    """,
                    sect_ids,
                ).fetchall()
                member_counts = {int(row["sect_id"]): int(row["c"] or 0) for row in count_rows}

            rankings = []
            for index, row in enumerate(sect_rows, start=1):
                sect_id = int(row["sect_id"])
                rankings.append(
                    {
                        "rank": index,
                        "sect_id": sect_id,
                        "name": row["sect_name"],
                        "owner_name": owners.get(row["sect_owner"], row["sect_owner"]),
                        "scale": int(row["sect_scale"] or 0),
                        "used_stone": int(row["sect_used_stone"] or 0),
                        "materials": int(row["sect_materials"] or 0),
                        "fairyland": int(row["sect_fairyland"] or 0),
                        "member_count": member_counts.get(sect_id, 0),
                    }
                )

            player_sect = None
            player_sect_id = int(player["sect_id"] or 0) if player else 0
            if player and player_sect_id > 0:
                sect = conn.execute(
                    """
                    SELECT sect_id, sect_name, sect_owner, sect_scale, sect_used_stone,
                           sect_fairyland, sect_materials, mainbuff, secbuff, elixir_room_level
                    FROM sects
                    WHERE sect_id = ?
                    """,
                    (player_sect_id,),
                ).fetchone()
                if sect:
                    members = conn.execute(
                        """
                        SELECT user_id, user_name, level_index, cultivation_type, sect_position, sect_contribution
                        FROM players
                        WHERE sect_id = ?
                        ORDER BY sect_position ASC, sect_contribution DESC, experience DESC
                        LIMIT 10
                        """,
                        (player_sect_id,),
                    ).fetchall()

                    owner_name = owners.get(sect["sect_owner"])
                    if not owner_name:
                        owner_row = conn.execute(
                            "SELECT user_id, user_name FROM players WHERE user_id = ?",
                            (sect["sect_owner"],),
                        ).fetchone()
                        owner_name = self._display_name(owner_row) if owner_row else sect["sect_owner"]

                    player_sect = {
                        "sect_id": int(sect["sect_id"]),
                        "name": sect["sect_name"],
                        "owner_name": owner_name,
                        "scale": int(sect["sect_scale"] or 0),
                        "used_stone": int(sect["sect_used_stone"] or 0),
                        "materials": int(sect["sect_materials"] or 0),
                        "fairyland": int(sect["sect_fairyland"] or 0),
                        "mainbuff": int(sect["mainbuff"] or 0),
                        "secbuff": int(sect["secbuff"] or 0),
                        "elixir_room_level": int(sect["elixir_room_level"] or 0),
                        "member_count": len(members),
                        "player_position_name": SECT_POSITIONS.get(int(player["sect_position"] or 4), "\u6210\u5458"),
                        "player_contribution": int(player["sect_contribution"] or 0),
                        "members": [
                            {
                                "name": self._display_name(member),
                                "level_name": self._level_name(
                                    member["cultivation_type"],
                                    int(member["level_index"] or 0),
                                ),
                                "position_name": SECT_POSITIONS.get(int(member["sect_position"] or 4), "\u6210\u5458"),
                                "contribution": int(member["sect_contribution"] or 0),
                            }
                            for member in members
                        ],
                    }

        return {
            "player_sect": player_sect,
            "rankings": rankings,
            "empty_state": "\u5f53\u524d\u8fd8\u6ca1\u6709\u4efb\u4f55\u5b97\u95e8\uff0c\u53ef\u7ee7\u7eed\u901a\u8fc7 Bot \u6307\u4ee4\u521b\u5efa\u5b97\u95e8\u540e\u518d\u6765\u67e5\u770b\u3002",
        }


    def get_bounty_preview(self, user_id: str) -> dict[str, Any]:
        difficulties = self.bounty_config.get("difficulties", {})
        templates = self.bounty_config.get("templates", [])

        available = []
        for item in templates[:8]:
            reward = item.get("reward", {}) if isinstance(item, dict) else {}
            diff_key = str(item.get("difficulty", ""))
            diff_cfg = difficulties.get(diff_key, {}) if isinstance(difficulties, dict) else {}
            available.append(
                {
                    "id": int(item.get("id", 0) or 0),
                    "name": str(item.get("name", "\u672a\u77e5\u60ac\u8d4f")),
                    "category": str(item.get("category", "\u672a\u77e5\u5206\u7c7b")),
                    "difficulty": diff_key,
                    "difficulty_name": str(diff_cfg.get("name", diff_key or "\u672a\u77e5\u96be\u5ea6")),
                    "description": str(item.get("description", "")),
                    "min_target": int(item.get("min_target", 1) or 1),
                    "max_target": int(item.get("max_target", 1) or 1),
                    "time_limit_minutes": int(int(item.get("time_limit", 3600) or 3600) / 60),
                    "stone_reward": int(reward.get("stone", 0) or 0),
                    "exp_reward": int(reward.get("exp", 0) or 0),
                    "progress_tags": [str(tag) for tag in item.get("progress_tags", [])],
                }
            )

        active = None
        recent = []
        accept_cooldown_minutes = 0

        with self._connect() as conn:
            if self._table_exists(conn, "system_config"):
                row = conn.execute(
                    "SELECT value FROM system_config WHERE key = ?",
                    (f"bounty_abandon_cd_{user_id}",),
                ).fetchone()
                if row:
                    try:
                        accept_cooldown_minutes = max(0, int(int(row["value"]) - int(time.time())) // 60)
                    except Exception:
                        accept_cooldown_minutes = 0

            if self._table_exists(conn, "bounty_tasks"):
                active_row = conn.execute(
                    "SELECT * FROM bounty_tasks WHERE user_id = ? AND status = 1 ORDER BY start_time DESC LIMIT 1",
                    (user_id,),
                ).fetchone()
                history_rows = conn.execute(
                    "SELECT * FROM bounty_tasks WHERE user_id = ? ORDER BY start_time DESC LIMIT 6",
                    (user_id,),
                ).fetchall()

                if active_row:
                    rewards = self._safe_json(active_row["rewards"], {})
                    target = int(active_row["target_count"] or 1)
                    progress = int(active_row["current_progress"] or 0)
                    remaining_seconds = max(0, int(active_row["expire_time"] or 0) - int(time.time()))
                    active = {
                        "bounty_id": int(active_row["bounty_id"] or 0),
                        "name": active_row["bounty_name"],
                        "target_type": active_row["target_type"],
                        "target_count": target,
                        "current_progress": progress,
                        "progress_percent": round((progress / target) * 100, 1) if target > 0 else 0.0,
                        "remaining_minutes": remaining_seconds // 60,
                        "difficulty_name": str(rewards.get("difficulty_name", rewards.get("difficulty", "\u672a\u77e5\u96be\u5ea6"))),
                        "description": str(rewards.get("description", "")),
                        "stone_reward": int(rewards.get("stone", 0) or 0),
                        "exp_reward": int(rewards.get("exp", 0) or 0),
                    }

                status_map = {0: "\u672a\u5f00\u59cb", 1: "\u8fdb\u884c\u4e2d", 2: "\u5df2\u5b8c\u6210", 3: "\u5df2\u5931\u8d25"}
                for row in history_rows:
                    recent.append(
                        {
                            "name": row["bounty_name"],
                            "bounty_id": int(row["bounty_id"] or 0),
                            "status": int(row["status"] or 0),
                            "status_name": status_map.get(int(row["status"] or 0), "\u672a\u77e5\u72b6\u6001"),
                            "target_count": int(row["target_count"] or 0),
                            "current_progress": int(row["current_progress"] or 0),
                            "target_type": row["target_type"],
                        }
                    )

        return {
            "active": active,
            "available": available,
            "recent": recent,
            "accept_cooldown_minutes": accept_cooldown_minutes,
            "empty_state": "\u5f53\u524d\u6ca1\u6709\u60ac\u8d4f\u8bb0\u5f55\uff0c\u53ef\u901a\u8fc7 Bot \u6307\u4ee4 /\u60ac\u8d4f\u4efb\u52a1 \u67e5\u770b\u5e76\u63a5\u53d6\u60ac\u8d4f\u3002",
        }

    def get_dual_cultivation_preview(self, user_id: str) -> dict[str, Any]:
        preview = {
            "cooldown_minutes": 0,
            "last_dual_at": None,
            "pending_request": None,
            "request_expire_minutes": 5,
            "cooldown_hours": 1,
            "exp_bonus_percent": 10,
            "max_exp_ratio": 3.0,
            "empty_state": "当前没有待处理的双修请求，可通过 Bot 指令 /双修 @某人 发起请求。",
        }

        with self._connect() as conn:
            if self._table_exists(conn, "dual_cultivation"):
                row = conn.execute(
                    "SELECT last_dual_time FROM dual_cultivation WHERE user_id = ?",
                    (user_id,),
                ).fetchone()
                if row and row["last_dual_time"]:
                    last_dual_at = int(row["last_dual_time"])
                    preview["last_dual_at"] = last_dual_at
                    preview["cooldown_minutes"] = max(0, (last_dual_at + 3600 - int(time.time())) // 60)

            if self._table_exists(conn, "dual_cultivation_requests"):
                now = int(time.time())
                request = conn.execute(
                    """
                    SELECT id, from_id, from_name, target_id, created_at, expires_at
                    FROM dual_cultivation_requests
                    WHERE target_id = ? AND expires_at > ?
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (user_id, now),
                ).fetchone()
                if request:
                    initiator = conn.execute(
                        """
                        SELECT user_id, user_name, level_index, cultivation_type, experience
                        FROM players
                        WHERE user_id = ?
                        """,
                        (request["from_id"],),
                    ).fetchone()
                    preview["pending_request"] = {
                        "request_id": int(request["id"]),
                        "from_name": request["from_name"],
                        "from_user_id": request["from_id"],
                        "expires_in_minutes": max(0, (int(request["expires_at"]) - now) // 60),
                        "level_name": self._level_name(
                            initiator["cultivation_type"],
                            int(initiator["level_index"] or 0),
                        ) if initiator else "未知境界",
                        "experience": int(initiator["experience"] or 0) if initiator else 0,
                    }

        return preview


class WebPreviewHandler(SimpleHTTPRequestHandler):
    repo: WebPreviewRepository | None = None
    db_path: Path | None = None

    def __init__(self, *args, directory=None, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def log_message(self, format, *args):
        print("[web-preview]", format % args)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._handle_api(parsed)
            return
        if parsed.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def _send_json(self, payload: dict[str, Any], status: int = HTTPStatus.OK):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_api(self, parsed):
        if not self.repo or not self.db_path:
            self._send_json(
                {
                    "ok": False,
                    "error": "数据库未配置",
                },
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return

        if parsed.path == "/api/health":
            self._send_json(
                {
                    "ok": True,
                    "db_path": str(self.db_path),
                }
            )
            return

        if parsed.path == "/api/players":
            self._send_json(
                {
                    "ok": True,
                    "players": self.repo.get_players(),
                    "world": self.repo.get_world_summary(),
                }
            )
            return

        if parsed.path == "/api/dashboard":
            params = parse_qs(parsed.query)
            user_id = (params.get("user_id") or [""])[0].strip()
            if not user_id:
                self._send_json({"ok": False, "error": "缺少 user_id"}, status=HTTPStatus.BAD_REQUEST)
                return
            try:
                dashboard = self.repo.get_dashboard(user_id)
            except KeyError:
                self._send_json({"ok": False, "error": f"未找到玩家：{user_id}"}, status=HTTPStatus.NOT_FOUND)
                return

            self._send_json({"ok": True, **dashboard})
            return

        self._send_json({"ok": False, "error": "未知接口"}, status=HTTPStatus.NOT_FOUND)


def parse_args() -> argparse.Namespace:
    defaults = load_web_server_config()
    parser = argparse.ArgumentParser(
        description="\u4fee\u4ed9 Web \u9884\u89c8\u670d\u52a1"
    )
    parser.add_argument(
        "--host",
        default=None,
        help="\u76d1\u542c\u5730\u5740\uff0c\u9ed8\u8ba4\u8bfb\u53d6 config/game_config.json \u4e2d\u7684 web_server.host\uff0c\u7f3a\u7701\u4e3a 0.0.0.0",
    )
    parser.add_argument(
        "--port",
        default=None,
        type=int,
        help="\u76d1\u542c\u7aef\u53e3\uff0c\u9ed8\u8ba4\u8bfb\u53d6 config/game_config.json \u4e2d\u7684 web_server.port\uff0c\u7f3a\u7701\u4e3a 8765",
    )
    parser.add_argument("--db", type=Path, default=detect_default_db(), help="\u6570\u636e\u5e93\u6587\u4ef6\u8def\u5f84")
    args = parser.parse_args()
    if not args.host:
        args.host = defaults["host"]
    if args.port is None:
        args.port = defaults["port"]
    return args


def main():
    args = parse_args()
    db_path = args.db
    if not db_path or not db_path.exists():
        raise SystemExit(
            "未找到数据库文件，请使用 --db 指定路径，例如：\n"
            "python web_preview_server.py --db F:\\Download\\xiuxian_data_lite.db"
        )

    WebPreviewHandler.repo = WebPreviewRepository(db_path)
    WebPreviewHandler.db_path = db_path

    server = ThreadingHTTPServer((args.host, args.port), WebPreviewHandler)
    print(f"修仙 Web 预览已启动：http://{args.host}:{args.port}")
    print(f"当前数据库：{db_path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
