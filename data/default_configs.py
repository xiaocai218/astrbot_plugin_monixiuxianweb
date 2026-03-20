SECT_CONFIG = {
    "create_cost": 10000,
    "create_level_required": 3,
    "positions": {
        "0": {"name": "宗主", "permission": 10},
        "1": {"name": "长老", "permission": 8},
        "2": {"name": "亲传弟子", "permission": 5},
        "3": {"name": "内门弟子", "permission": 2},
        "4": {"name": "外门弟子", "permission": 1},
    },
    "scale_ratio": 10,
}


BOSS_CONFIG = {
    "spawn_interval": 3600,
    "levels": [
        {"name": "炼气", "level_index": 0, "hp_mult": 1.0, "atk_mult": 1.0, "reward_mult": 1.0},
        {"name": "筑基", "level_index": 3, "hp_mult": 1.5, "atk_mult": 1.2, "reward_mult": 1.5},
        {"name": "金丹", "level_index": 6, "hp_mult": 2.0, "atk_mult": 1.5, "reward_mult": 2.0},
        {"name": "元婴", "level_index": 9, "hp_mult": 2.5, "atk_mult": 1.8, "reward_mult": 2.5},
        {"name": "化神", "level_index": 12, "hp_mult": 3.0, "atk_mult": 2.0, "reward_mult": 3.0},
        {"name": "炼虚", "level_index": 15, "hp_mult": 4.0, "atk_mult": 2.5, "reward_mult": 4.0},
        {"name": "合体", "level_index": 18, "hp_mult": 5.0, "atk_mult": 3.0, "reward_mult": 5.0},
        {"name": "大乘", "level_index": 21, "hp_mult": 6.0, "atk_mult": 3.5, "reward_mult": 6.0},
    ],
}


RIFT_CONFIG = {
    "default_duration": 1800,
    "open_refresh_interval": 3600,
    "open_chances_by_level": {
        "1": 100,
        "2": 70,
        "3": 45,
        "4": 25,
        "5": 12,
    },
    "rifts": [
        {"id": 1, "name": "青云秘境", "level": 1, "required_level": 0, "exp_range": [500, 1500], "gold_range": [200, 800]},
        {"id": 2, "name": "落日峡谷", "level": 2, "required_level": 5, "exp_range": [1500, 4000], "gold_range": [500, 2000]},
        {"id": 3, "name": "万妖洞", "level": 3, "required_level": 10, "exp_range": [3000, 8000], "gold_range": [1000, 5000]},
        {"id": 4, "name": "玄冰地宫", "level": 4, "required_level": 16, "exp_range": [5000, 15000], "gold_range": [2000, 10000]},
        {"id": 5, "name": "上古遗迹", "level": 5, "required_level": 22, "exp_range": [10000, 30000], "gold_range": [5000, 20000]},
    ],
}


ALCHEMY_CONFIG = {
    "recipes": {
        "1": {
            "name": "聚气丹",
            "level_required": 0,
            "materials": {"灵草": 3, "灵石": 100},
            "success_rate": 80,
            "effect": {"type": "exp", "value": 1000},
            "desc": "增加1000修为",
        },
        "2": {
            "name": "筑基丹",
            "level_required": 2,
            "materials": {"灵草": 5, "灵石": 500},
            "success_rate": 60,
            "effect": {"type": "exp", "value": 5000},
            "desc": "增加5000修为",
        },
        "3": {
            "name": "金丹",
            "level_required": 5,
            "materials": {"灵草": 10, "灵石": 2000},
            "success_rate": 40,
            "effect": {"type": "exp", "value": 20000},
            "desc": "增加20000修为",
        },
        "4": {
            "name": "回春丹",
            "level_required": 1,
            "materials": {"灵草": 2, "灵石": 200},
            "success_rate": 70,
            "effect": {"type": "hp_restore", "value": 50},
            "desc": "恢复50%气血",
        },
        "5": {
            "name": "聚灵丹",
            "level_required": 1,
            "materials": {"灵草": 2, "灵石": 200},
            "success_rate": 70,
            "effect": {"type": "mp_restore", "value": 50},
            "desc": "恢复50%真元",
        },
    }
}
