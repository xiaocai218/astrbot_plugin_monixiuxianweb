import json
from pathlib import Path
from typing import Any

from astrbot.api import logger

from .data.default_configs import ALCHEMY_CONFIG, BOSS_CONFIG, RIFT_CONFIG, SECT_CONFIG


class ConfigManager:
    """统一加载插件配置与静态数据。"""

    def __init__(self, base_dir: Path):
        self._base_dir = base_dir

        self.level_data: list[dict] = []
        self.body_level_data: list[dict] = []
        self.items_data: dict[str, dict] = {}
        self.weapons_data: dict[str, dict] = {}
        self.pills_data: dict[str, dict] = {}
        self.exp_pills_data: dict[str, dict] = {}
        self.utility_pills_data: dict[str, dict] = {}
        self.storage_rings_data: dict[str, dict] = {}
        self.alchemy_recipes: dict[str, dict] = {}

        self.sect_config: dict[str, Any] = {}
        self.boss_config: dict[str, Any] = {}
        self.rift_config: dict[str, Any] = {}
        self.alchemy_config: dict[str, Any] = {}
        self.game_config: dict[str, Any] = {}

        self._pill_names_cache: set[str] | None = None
        self._load_all()

    def get_level_data(self, cultivation_type: str = "灵修") -> list[dict]:
        """按修炼类型返回对应境界配置。"""
        if cultivation_type == "体修":
            return self.body_level_data
        return self.level_data

    def _load_json_list(self, file_path: Path) -> list[dict]:
        """读取列表格式 JSON，不存在或失败时返回空列表。"""
        if not file_path.exists():
            logger.warning(f"数据文件不存在，跳过加载: {file_path}")
            return []

        try:
            with open(file_path, "r", encoding="utf-8") as file:
                data = json.load(file)
            logger.info(f"成功加载 {file_path.name}，共 {len(data)} 条记录")
            return data
        except Exception as exc:
            logger.error(f"加载数据文件失败 {file_path}: {exc}")
            return []

    def _load_dict_by_name(self, file_path: Path) -> dict[str, dict]:
        """读取物品类配置，统一转成以 name 为 key 的字典。"""
        if not file_path.exists():
            logger.warning(f"物品配置不存在，跳过加载: {file_path}")
            return {}

        try:
            with open(file_path, "r", encoding="utf-8") as file:
                data = json.load(file)
        except Exception as exc:
            logger.error(f"加载物品配置失败 {file_path}: {exc}")
            return {}

        if isinstance(data, list):
            items = {
                item["name"]: item
                for item in data
                if isinstance(item, dict) and item.get("name")
            }
        elif isinstance(data, dict):
            items = {}
            for item_id, item_data in data.items():
                if not isinstance(item_data, dict) or not item_data.get("name"):
                    continue
                normalized = dict(item_data)
                normalized.setdefault("id", item_id)
                items[normalized["name"]] = normalized
        else:
            logger.error(f"物品配置格式不正确，应为 list 或 dict: {file_path}")
            return {}

        logger.info(f"成功加载 {file_path.name}，共 {len(items)} 个条目")
        return items

    def _load_config_with_default(self, file_path: Path, default_config: dict[str, Any]) -> dict[str, Any]:
        """读取配置文件；若不存在则写入默认配置后返回。"""
        if not file_path.exists():
            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(file_path, "w", encoding="utf-8") as file:
                    json.dump(default_config, file, ensure_ascii=False, indent=2)
                logger.info(f"已创建默认配置文件: {file_path.name}")
                return default_config
            except Exception as exc:
                logger.error(f"创建默认配置失败 {file_path}: {exc}")
                return default_config

        try:
            with open(file_path, "r", encoding="utf-8") as file:
                data = json.load(file)
            logger.info(f"成功加载配置文件: {file_path.name}")
            return data
        except Exception as exc:
            logger.error(f"加载配置文件失败 {file_path}: {exc}")
            return default_config

    def _load_all(self):
        """加载全部静态配置与游戏配置。"""
        config_dir = self._base_dir / "config"

        self.level_data = self._load_json_list(config_dir / "level_config.json")
        self.body_level_data = self._load_json_list(config_dir / "body_level_config.json")

        self.items_data = self._load_dict_by_name(config_dir / "items.json")
        self.weapons_data = self._load_dict_by_name(config_dir / "weapons.json")
        self.pills_data = self._load_dict_by_name(config_dir / "pills.json")
        self.exp_pills_data = self._load_dict_by_name(config_dir / "exp_pills.json")
        self.utility_pills_data = self._load_dict_by_name(config_dir / "utility_pills.json")
        self.storage_rings_data = self._load_dict_by_name(config_dir / "storage_rings.json")
        self.alchemy_recipes = self._load_dict_by_name(config_dir / "alchemy_recipes.json")

        self.sect_config = self._load_config_with_default(config_dir / "sect_config.json", SECT_CONFIG)
        self.boss_config = self._load_config_with_default(config_dir / "boss_config.json", BOSS_CONFIG)
        self.rift_config = self._load_config_with_default(config_dir / "rift_config.json", RIFT_CONFIG)
        self.alchemy_config = self._load_config_with_default(config_dir / "alchemy_config.json", ALCHEMY_CONFIG)
        self.game_config = self._load_config_with_default(
            config_dir / "game_config.json",
            {
                "web_server": {
                    "host": "0.0.0.0",
                    "port": 8765,
                    "comment": "Web 游戏预览服务监听配置",
                }
            },
        )

        self.invalidate_cache()
        logger.info(
            "配置管理器初始化完成："
            f"灵修境界 {len(self.level_data)} 条，"
            f"体修境界 {len(self.body_level_data)} 条，"
            f"物品 {len(self.items_data)} 条，"
            f"武器 {len(self.weapons_data)} 条。"
        )

    def is_pill(self, item_name: str) -> bool:
        """判断物品名是否属于任意丹药配置。"""
        if item_name in self.pills_data:
            return True
        if item_name in self.exp_pills_data:
            return True
        if item_name in self.utility_pills_data:
            return True

        item_config = self.items_data.get(item_name)
        return bool(item_config and item_config.get("type") == "丹药")

    def get_all_pill_names(self) -> set[str]:
        """返回全部已注册丹药名。"""
        if self._pill_names_cache is not None:
            return self._pill_names_cache

        pill_names = set()
        pill_names.update(self.pills_data.keys())
        pill_names.update(self.exp_pills_data.keys())
        pill_names.update(self.utility_pills_data.keys())

        for name, item in self.items_data.items():
            if isinstance(item, dict) and item.get("type") == "丹药":
                pill_names.add(name)

        self._pill_names_cache = pill_names
        return pill_names

    def invalidate_cache(self):
        """清理运行期缓存。"""
        self._pill_names_cache = None
