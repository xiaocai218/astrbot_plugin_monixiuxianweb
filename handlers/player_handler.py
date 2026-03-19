"""玩家基础信息与修炼相关处理器。"""

import random
import time
from datetime import datetime

from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent

from ..config_manager import ConfigManager
from ..core import CultivationManager, PillManager
from ..data import DataBase
from ..managers.battle_hp_service import BattleHpService
from ..managers.boss_challenge_service import BossChallengeService
from ..managers.combat_manager import CombatManager
from ..managers.pet_manager import PetManager
from ..models import Player
from ..models_extended import UserStatus
from ..utils.image_generator import ImageGenerator
from .utils import player_required

CMD_START_XIUXIAN = "我要修仙"
CMD_PLAYER_INFO = "我的信息"
CMD_START_CULTIVATION = "闭关"
CMD_END_CULTIVATION = "出关"
CMD_CHECK_IN = "签到"
REBIRTH_COOLDOWN = 7 * 24 * 3600
REROLL_ROOT_COST = 10000

__all__ = ["PlayerHandler"]


class PlayerHandler:
    """处理建号、信息、闭关、签到与重修。"""

    def __init__(self, db: DataBase, config: AstrBotConfig, config_manager: ConfigManager):
        self.db = db
        self.config = config
        self.config_manager = config_manager
        self.cultivation_manager = CultivationManager(config, config_manager)
        self.pill_manager = PillManager(self.db, self.config_manager)
        self.battle_hp_service = BattleHpService(self.db, CombatManager(), config_manager)
        self.boss_challenge_service = BossChallengeService(self.db)
        self.pet_manager = PetManager(self.db)
        self.image_generator = ImageGenerator()
        self.enlightenment_manager = None

    async def _resolve_display_battle_hp(self, player: Player):
        """统一结算展示用战斗HP。"""
        return await self.battle_hp_service.resolve_player_battle_status(player)

    async def _resolve_display_status(self, player: Player) -> str:
        """返回 /我的信息 中显示的真实状态。"""
        user_cd = await self.db.ext.get_user_cd(player.user_id)
        if user_cd and user_cd.type != UserStatus.IDLE:
            return UserStatus.get_name(user_cd.type)
        return player.state or "空闲"

    async def _get_pet_display_name(self, user_id: str) -> str:
        equipped_pet = await self.pet_manager.get_equipped_pet(user_id)
        if not equipped_pet or equipped_pet.get("state") != "active":
            return "未携带"

        pet_rank = self.pet_manager.RANK_LABELS.get(
            equipped_pet.get("rank", ""),
            equipped_pet.get("rank", "未知"),
        )
        pet_skill_1 = self.pet_manager.SKILL_LABELS.get(
            equipped_pet.get("skill_1", ""),
            equipped_pet.get("skill_1", ""),
        )
        pet_skill_2 = self.pet_manager.SKILL_LABELS.get(
            equipped_pet.get("skill_2", ""),
            equipped_pet.get("skill_2", ""),
        )
        return f"{equipped_pet['name']}（{pet_rank}，{pet_skill_1}/{pet_skill_2}）"

    async def handle_start_xiuxian(self, event: AstrMessageEvent, cultivation_type: str = ""):
        """创建角色。"""
        user_id = event.get_sender_id()

        if await self.db.get_player_by_id(user_id):
            yield event.plain_result("道友，你已经踏入仙途，无需重复创建角色。")
            return

        cultivation_type = cultivation_type.strip()
        if not cultivation_type:
            help_msg = (
                "欢迎踏入修仙之路\n"
                "━━━━━━━━━━━━━━\n"
                "请选择你的修炼方式：\n\n"
                "【灵修】以灵气为主，擅长术法\n"
                "  - 灵气较高\n"
                "  - 法伤成长较强\n"
                "  - 精神力稳定\n\n"
                "【体修】以气血为主，擅长肉身\n"
                "  - 气血较高\n"
                "  - 物伤与防御更强\n"
                "  - 精神力稳定\n\n"
                "使用方式：\n"
                f"  {CMD_START_XIUXIAN} 灵修\n"
                f"  {CMD_START_XIUXIAN} 体修"
            )
            yield event.plain_result(help_msg)
            return

        if cultivation_type not in ["灵修", "体修"]:
            yield event.plain_result("职业选择错误，请选择“灵修”或“体修”。")
            return

        new_player = self.cultivation_manager.generate_new_player_stats(user_id, cultivation_type)
        await self.db.create_player(new_player)

        root_name = new_player.spiritual_root.replace("灵根", "")
        root_description = self.cultivation_manager._get_root_description(root_name)
        reply_msg = (
            f"恭喜道友 {event.get_sender_name()} 踏上仙途\n"
            "━━━━━━━━━━━━━━\n"
            f"修炼方式：{new_player.cultivation_type}\n"
            f"灵根：{new_player.spiritual_root}\n"
            f"评价：{root_description}\n"
            f"启动资金：{new_player.gold} 灵石\n"
            "━━━━━━━━━━━━━━\n"
            f"发送“{CMD_PLAYER_INFO}”查看当前状态。"
        )
        yield event.plain_result(reply_msg)

    @player_required
    async def handle_player_info(self, player: Player, event: AstrMessageEvent):
        """查看玩家信息，优先输出图片卡片。"""
        display_name = event.get_sender_name()
        required_exp = player.get_required_exp(self.config_manager)

        await self.pill_manager.update_temporary_effects(player)
        pill_multipliers = self.pill_manager.calculate_pill_attribute_effects(player)

        from ..core import EquipmentManager

        equipment_manager = EquipmentManager(self.db, self.config_manager)
        equipped_items = equipment_manager.get_equipped_items(
            player,
            self.config_manager.items_data,
            self.config_manager.weapons_data,
        )
        total_attrs = player.get_total_attributes(equipped_items, pill_multipliers)

        combat_power = (
            int(total_attrs["physical_damage"])
            + int(total_attrs["magic_damage"])
            + int(total_attrs["physical_defense"])
            + int(total_attrs["magic_defense"])
            + int(total_attrs["mental_power"]) // 10
        )

        battle_hp, battle_hp_max, hp_recovering, boss_cooldown_remaining = await self._resolve_display_battle_hp(player)
        _boss_used_count, boss_remaining_count = await self.boss_challenge_service.get_daily_status(player.user_id)
        display_status = await self._resolve_display_status(player)

        sect_name = "无宗门"
        position_name = "散修"
        if player.sect_id and player.sect_id != 0:
            sect = await self.db.ext.get_sect_by_id(player.sect_id)
            if sect:
                sect_name = sect.sect_name
                if sect.sect_owner == player.user_id:
                    position_name = "宗主"
                elif player.sect_position == 1:
                    position_name = "长老"
                elif player.sect_position == 2:
                    position_name = "亲传弟子"
                elif player.sect_position == 3:
                    position_name = "内门弟子"
                else:
                    position_name = "外门弟子"

        weapon_name = player.weapon if player.weapon else "无"
        armor_name = player.armor if player.armor else "无"
        technique_name = player.main_technique if player.main_technique else "无"
        breakthrough_rate = f"+{player.level_up_rate}%" if player.level_up_rate > 0 else "0%"
        dao_hao = player.user_name if player.user_name else display_name
        pet_name = await self._get_pet_display_name(player.user_id)

        tips = []
        if hp_recovering:
            if boss_cooldown_remaining > 0:
                minutes = boss_cooldown_remaining // 60
                seconds = boss_cooldown_remaining % 60
                tips.append(f"Boss冷却：{minutes}分{seconds}秒")
            tips.append("战斗HP恢复中：每分钟恢复10%，约10分钟恢复满血")

        loan = await self.db.ext.get_active_loan(player.user_id)
        if loan:
            now = int(time.time())
            remaining_seconds = loan["due_at"] - now
            remaining_days = remaining_seconds // 86400
            remaining_hours = (remaining_seconds % 86400) // 3600
            days_borrowed = max(1, (now - loan["borrowed_at"]) // 86400)
            interest = int(loan["principal"] * loan["interest_rate"] * days_borrowed)
            total_due = loan["principal"] + interest
            loan_type_name = "突破贷款" if loan["loan_type"] == "breakthrough" else "普通贷款"

            if remaining_seconds <= 0:
                time_str = "已逾期"
            elif remaining_days <= 0:
                time_str = f"{remaining_hours}小时"
            elif remaining_days <= 1:
                time_str = f"{remaining_days}天{remaining_hours}小时"
            else:
                time_str = f"{remaining_days}天"

            tips.append(f"贷款：{loan_type_name}，应还 {total_due:,} 灵石，剩余 {time_str}")

        if player.cultivation_type == "体修":
            resource_name = "气血"
            resource_value = f"{player.blood_qi}/{total_attrs.get('max_blood_qi', 0)}"
            primary_damage = total_attrs["physical_damage"]
            secondary_damage = total_attrs["magic_damage"]
            primary_defense = total_attrs["physical_defense"]
            secondary_defense = total_attrs["magic_defense"]
        else:
            resource_name = "灵气"
            resource_value = f"{player.spiritual_qi}/{total_attrs.get('max_spiritual_qi', 0)}"
            primary_damage = total_attrs["magic_damage"]
            secondary_damage = total_attrs["physical_damage"]
            primary_defense = total_attrs["magic_defense"]
            secondary_defense = total_attrs["physical_defense"]

        detail_map = {
            "basic_info": [
                ("道号", dao_hao),
                ("境界", player.get_level(self.config_manager)),
                ("修为", f"{int(player.experience):,}/{int(required_exp):,}"),
                ("灵石", f"{player.gold:,}"),
                ("战力", f"{combat_power:,}"),
                ("灵根", player.spiritual_root),
                ("突破加成", breakthrough_rate),
            ],
            "cultivation_info": [
                ("修炼方式", player.cultivation_type),
                ("状态", display_status),
                ("寿命", str(player.lifespan)),
                ("精神力", str(total_attrs["mental_power"])),
                ("战斗HP", f"{battle_hp}/{battle_hp_max}"),
                ("Boss次数", f"今日剩余 {boss_remaining_count}/{BossChallengeService.BOSS_DAILY_CHALLENGE_LIMIT}"),
                (resource_name, resource_value),
                ("主伤害", str(primary_damage)),
                ("副伤害", str(secondary_damage)),
                ("主防御", str(primary_defense)),
                ("副防御", str(secondary_defense)),
            ],
            "equipment_info": [
                ("主修功法", technique_name),
                ("法器", weapon_name),
                ("防具", armor_name),
                ("灵宠", pet_name),
            ],
            "other_info": [
                ("宗门", sect_name),
                ("职位", position_name),
            ],
            "tips": tips,
        }

        image_path = await self.image_generator.generate_user_info_card(player.user_id, detail_map)
        if image_path:
            yield event.image_result(image_path)
            return

        reply_lines = [
            f"📋 道友 {dao_hao} 的信息",
            "━━━━━━━━━━━━━━━",
            "【基本信息】",
            f"  道号：{dao_hao}",
            f"  境界：{player.get_level(self.config_manager)}",
            f"  修为：{int(player.experience):,}/{int(required_exp):,}",
            f"  灵石：{player.gold:,}",
            f"  战力：{combat_power:,}",
            f"  灵根：{player.spiritual_root}",
            f"  突破加成：{breakthrough_rate}",
            "",
            "【修炼属性】",
            f"  修炼方式：{player.cultivation_type}",
            f"  状态：{display_status}",
            f"  寿命：{player.lifespan}",
            f"  精神力：{total_attrs['mental_power']}",
            f"  战斗HP：{battle_hp}/{battle_hp_max}",
            f"  Boss次数：今日剩余 {boss_remaining_count}/{BossChallengeService.BOSS_DAILY_CHALLENGE_LIMIT}",
            f"  {resource_name}：{resource_value}",
            f"  主伤害：{primary_damage}",
            f"  副伤害：{secondary_damage}",
            f"  主防御：{primary_defense}",
            f"  副防御：{secondary_defense}",
        ]

        if tips:
            reply_lines.extend(["", "【状态提示】"])
            reply_lines.extend([f"  {tip}" for tip in tips])

        reply_lines.extend(
            [
                "",
                "【装备信息】",
                f"  主修功法：{technique_name}",
                f"  法器：{weapon_name}",
                f"  防具：{armor_name}",
                f"  灵宠：{pet_name}",
                "",
                "【宗门信息】",
                f"  所在宗门：{sect_name}",
                f"  宗门职位：{position_name}",
                "━━━━━━━━━━━━━━━",
            ]
        )
        yield event.plain_result("\n".join(reply_lines))

    @player_required
    async def handle_start_cultivation(self, player: Player, event: AstrMessageEvent):
        """开始闭关。"""
        if player.state == "修炼中":
            yield event.plain_result("道友已在闭关中，请勿重复进入。")
            return

        user_cd = await self.db.ext.get_user_cd(player.user_id)
        if user_cd and user_cd.type != UserStatus.IDLE:
            current_status = UserStatus.get_name(user_cd.type)
            yield event.plain_result(f"道友当前正处于【{current_status}】状态，无法闭关修炼。")
            return

        player.state = "修炼中"
        player.cultivation_start_time = int(time.time())
        await self.db.update_player(player)
        await self.db.ext.set_user_busy(player.user_id, UserStatus.CULTIVATING, 0)

        yield event.plain_result(
            "🧘 道友已进入闭关状态\n"
            "━━━━━━━━━━━━━━\n"
            "闭关期间，你将潜心修炼。\n"
            f"发送“{CMD_END_CULTIVATION}”结束闭关。"
        )

    @player_required
    async def handle_end_cultivation(self, player: Player, event: AstrMessageEvent):
        """结束闭关。"""
        if player.state != "修炼中":
            yield event.plain_result("道友当前并未闭关，无需出关。")
            return

        if player.cultivation_start_time == 0:
            yield event.plain_result("数据异常：未记录闭关开始时间。")
            return

        end_time = int(time.time())
        duration_seconds = end_time - player.cultivation_start_time
        duration_minutes = duration_seconds // 60

        if duration_minutes < 1:
            yield event.plain_result("道友闭关时间不足1分钟，未获得修为，请继续闭关。")
            return

        base_minutes = 1440
        realm_bonus = (player.level_index // 9) * 360
        max_cultivation_minutes = base_minutes + realm_bonus
        effective_minutes = min(duration_minutes, max_cultivation_minutes)
        exceeded_time = duration_minutes > max_cultivation_minutes

        await self.pill_manager.update_temporary_effects(player)
        pill_multipliers = self.pill_manager.calculate_pill_attribute_effects(player)

        technique_bonus = 0.0
        if player.main_technique:
            from ..core import EquipmentManager

            equipment_manager = EquipmentManager(self.db, self.config_manager)
            equipped_items = equipment_manager.get_equipped_items(
                player,
                self.config_manager.items_data,
                self.config_manager.weapons_data,
            )
            for item in equipped_items:
                if item.item_type == "main_technique":
                    technique_bonus = item.exp_multiplier
                    break

        gained_exp = self.cultivation_manager.calculate_cultivation_exp(
            player,
            effective_minutes,
            technique_bonus,
            pill_multipliers,
        )

        enlightenment_msg = ""
        if self.enlightenment_manager:
            triggered, msg, bonus_exp = await self.enlightenment_manager.try_enlightenment(player, gained_exp)
            if triggered:
                gained_exp += bonus_exp
                enlightenment_msg = f"\n\n{msg}"

        player.experience += gained_exp
        player.state = "空闲"
        player.cultivation_start_time = 0
        await self.db.update_player(player)
        await self.db.ext.set_user_free(player.user_id)

        hours = duration_minutes // 60
        minutes = duration_minutes % 60
        time_str = ""
        if hours > 0:
            time_str += f"{hours}小时"
        if minutes > 0:
            time_str += f"{minutes}分钟"

        exceed_msg = ""
        if exceeded_time:
            effective_hours = max_cultivation_minutes // 60
            exceed_msg = f"\n⚠️ 闭关超过{effective_hours}小时，仅计算前{effective_hours}小时修为"

        reply_msg = (
            "🎵 道友出关成功\n"
            "━━━━━━━━━━━━━━\n"
            f"闭关时长：{time_str}\n"
            f"获得修为：{gained_exp:,}{exceed_msg}\n"
            f"当前修为：{player.experience:,}\n"
            "━━━━━━━━━━━━━━\n"
            "道友已回归红尘，可继续修行。"
        )
        reply_msg += enlightenment_msg
        yield event.plain_result(reply_msg)

    @player_required
    async def handle_check_in(self, player: Player, event: AstrMessageEvent):
        """每日签到。"""
        today = datetime.now().strftime("%Y-%m-%d")
        if player.last_check_in_date == today:
            yield event.plain_result("📝 道友今日已经签到过了，请明日再来。")
            return

        values_config = self.config.get("VALUES", {}) if hasattr(self.config, "get") else {}
        check_in_gold_min = values_config.get("CHECK_IN_GOLD_MIN", 50)
        check_in_gold_max = values_config.get("CHECK_IN_GOLD_MAX", 500)
        if check_in_gold_min > check_in_gold_max:
            check_in_gold_min, check_in_gold_max = check_in_gold_max, check_in_gold_min

        check_in_gold = random.randint(check_in_gold_min, check_in_gold_max)
        player.gold += check_in_gold
        player.last_check_in_date = today
        await self.db.update_player(player)

        reply_msg = (
            "✅ 签到成功\n"
            "━━━━━━━━━━━━━━\n"
            f"获得灵石：{check_in_gold}\n"
            f"当前灵石：{player.gold}\n"
            "━━━━━━━━━━━━━━\n"
            "明日再来，莫要忘记。"
        )
        yield event.plain_result(reply_msg)

    @player_required
    async def handle_rebirth(self, player: Player, event: AstrMessageEvent, confirm_text: str = ""):
        """弃道重修。"""
        user_cd = await self.db.ext.get_user_cd(player.user_id)
        if user_cd and user_cd.type != UserStatus.IDLE:
            status_name = UserStatus.get_name(user_cd.type)
            yield event.plain_result(f"你当前正处于【{status_name}】状态，无法弃道重修。")
            return

        if player.state != "空闲":
            yield event.plain_result("只有处于空闲状态时才能弃道重修，请先结束其他活动。")
            return

        loan = await self.db.ext.get_active_loan(player.user_id)
        if loan:
            yield event.plain_result("你仍有未结清的灵石贷款，无法重修，请先还款。")
            return

        key = f"rebirth_last_{player.user_id}"
        last_ts = await self.db.ext.get_system_config(key)
        now = int(time.time())
        if last_ts:
            diff = now - int(last_ts)
            if diff < REBIRTH_COOLDOWN:
                remaining = REBIRTH_COOLDOWN - diff
                days = remaining // 86400
                hours = (remaining % 86400) // 3600
                minutes = (remaining % 3600) // 60
                yield event.plain_result(
                    "🚢 弃道重修冷却中\n"
                    "━━━━━━━━━━━━━━\n"
                    f"距离下次重修还需：{days}天{hours}小时{minutes}分钟"
                )
                return

        if confirm_text.strip() != "确认":
            yield event.plain_result(
                "⚠️ 弃道重修将删除当前角色的所有数据，且无法撤回。\n"
                "限制：每7天只能重修一次，且必须处于空闲状态、无贷款时使用。\n"
                "━━━━━━━━━━━━━━\n"
                "若你已做好准备，请发送：\n"
                "弃道重修 确认"
            )
            return

        await self.db.delete_player_cascade(player.user_id)
        await self.db.ext.set_system_config(key, str(now))

        yield event.plain_result(
            "🗙 你选择了弃道重修，旧生一切化为尘埃。\n"
            "━━━━━━━━━━━━━━\n"
            "可立刻使用“我要修仙”重新踏上仙途。\n"
            "7天内不可再次重修。"
        )

    @player_required
    async def handle_reroll_root(self, player: Player, event: AstrMessageEvent):
        """逆天改命：花费灵石重置灵根。"""
        user_cd = await self.db.ext.get_user_cd(player.user_id)
        if user_cd and user_cd.type != UserStatus.IDLE:
            status_name = UserStatus.get_name(user_cd.type)
            yield event.plain_result(f"你当前正处于【{status_name}】状态，无法逆天改命。")
            return

        if player.state != "空闲":
            yield event.plain_result("只有处于空闲状态时才能逆天改命，请先结束其他活动。")
            return

        if player.gold < REROLL_ROOT_COST:
            yield event.plain_result(
                "灵石不足\n"
                f"逆天改命需要 {REROLL_ROOT_COST:,} 灵石\n"
                f"当前灵石：{player.gold:,}"
            )
            return

        old_root = player.spiritual_root
        old_root_name = old_root.replace("灵根", "")
        old_description = self.cultivation_manager._get_root_description(old_root_name)

        new_root_name = self.cultivation_manager._get_random_spiritual_root()
        new_root = f"{new_root_name}灵根"
        new_description = self.cultivation_manager._get_root_description(new_root_name)

        player.gold -= REROLL_ROOT_COST
        player.spiritual_root = new_root
        await self.db.update_player(player)

        old_quality = self._get_root_quality(old_root_name)
        new_quality = self._get_root_quality(new_root_name)
        if new_quality > old_quality:
            result_emoji = "🎇"
            result_text = "天命改写，灵根蜕变！"
        elif new_quality < old_quality:
            result_emoji = "😧"
            result_text = "造化弄人，灵根退化了。"
        else:
            result_emoji = "😜"
            result_text = "命运轮转，灵根发生了更替。"

        yield event.plain_result(
            f"{result_emoji} 逆天改命 {result_emoji}\n"
            "━━━━━━━━━━━━━━\n"
            f"消耗灵石：{REROLL_ROOT_COST:,}\n"
            f"原灵根：{old_root}\n"
            f"  {old_description}\n"
            f"新灵根：{new_root}\n"
            f"  {new_description}\n"
            f"结果：{result_text}\n"
            f"剩余灵石：{player.gold:,}"
        )

    def _get_root_quality(self, root_name: str) -> int:
        """为逆天改命结果提供灵根品级比较。"""
        quality_map = {
            "伪": 0,
            "金木水火": 1,
            "金木水土": 1,
            "金木火土": 1,
            "金水火土": 1,
            "木水火土": 1,
            "金木水": 2,
            "金木火": 2,
            "金木土": 2,
            "金水火": 2,
            "金水土": 2,
            "金火土": 2,
            "木水火": 2,
            "木水土": 2,
            "木火土": 2,
            "水火土": 2,
            "金木": 3,
            "金水": 3,
            "金火": 3,
            "金土": 3,
            "木水": 3,
            "木火": 3,
            "木土": 3,
            "水火": 3,
            "水土": 3,
            "火土": 3,
            "金": 4,
            "木": 4,
            "水": 4,
            "火": 4,
            "土": 4,
            "雷": 5,
            "冰": 5,
            "风": 5,
            "暗": 5,
            "光": 5,
            "天金": 6,
            "天木": 6,
            "天水": 6,
            "天火": 6,
            "天土": 6,
            "天雷": 6,
            "阴阳": 7,
            "融合": 7,
            "混沌": 8,
            "先天道体": 9,
            "神圣体质": 9,
        }
        return quality_map.get(root_name, 3)
