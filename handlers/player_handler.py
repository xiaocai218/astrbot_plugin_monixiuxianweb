# handlers/player_handler.py
import random
import time
from datetime import datetime

from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent

from ..battle_hp_utils import resolve_boss_battle_hp_state
from ..config_manager import ConfigManager
from ..core import CultivationManager, PillManager
from ..data import DataBase
from ..models import Player
from ..models_extended import UserStatus
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
    """玩家基础信息处理器。"""

    def __init__(self, db: DataBase, config: AstrBotConfig, config_manager: ConfigManager):
        self.db = db
        self.config = config
        self.config_manager = config_manager
        self.cultivation_manager = CultivationManager(config, config_manager)
        self.pill_manager = PillManager(self.db, self.config_manager)
        self.enlightenment_manager = None

    async def _resolve_display_battle_hp(self, player: Player):
        """Resolve current battle HP for info display, including Boss auto-recovery."""
        impart_info = await self.db.ext.get_impart_info(player.user_id)
        hp_buff = impart_info.impart_hp_per if impart_info else 0.0
        max_hp = int(player.experience * (1 + hp_buff) // 2)
        if max_hp <= 0:
            return player.hp, 0, False, 0

        current_hp = max(1, min(player.hp, max_hp)) if player.hp > 0 else max_hp
        user_cd = await self.db.ext.get_user_cd(player.user_id)
        if not user_cd:
            if current_hp != player.hp:
                player.hp = current_hp
                await self.db.update_player(player)
            return current_hp, max_hp, False, 0

        extra_data = user_cd.get_extra_data()
        recovery_enabled = bool(extra_data.get("boss_challenge_hp_recovering", 0))
        cooldown_until = int(extra_data.get("boss_challenge_cd_until", 0) or 0)
        cooldown_remaining = max(0, cooldown_until - int(time.time())) if cooldown_until else 0

        # 兼容旧数据或异常中断场景：只要战斗 HP 低于上限，就补建恢复锚点。
        if not recovery_enabled and current_hp < max_hp:
            started_at = max(0, cooldown_until - 300) if cooldown_until else int(time.time())
            extra_data["boss_challenge_hp_recovering"] = 1
            extra_data["boss_challenge_hp_recovery_base_hp"] = current_hp
            extra_data["boss_challenge_hp_recovery_started_at"] = started_at
            user_cd.set_extra_data(extra_data)
            await self.db.ext.update_user_cd(user_cd)
            recovery_enabled = True

        if recovery_enabled:
            base_hp = int(extra_data.get("boss_challenge_hp_recovery_base_hp", 0) or 0)
            started_at = int(extra_data.get("boss_challenge_hp_recovery_started_at", 0) or 0)
            if base_hp <= 0:
                base_hp = current_hp if current_hp > 0 else 1
            if started_at <= 0:
                started_at = max(0, cooldown_until - 300) if cooldown_until else int(time.time())

            elapsed = max(0, int(time.time()) - started_at)
            if elapsed >= 600:
                current_hp = max_hp
                extra_data.pop("boss_challenge_hp_recovering", None)
                extra_data.pop("boss_challenge_hp_recovery_base_hp", None)
                extra_data.pop("boss_challenge_hp_recovery_started_at", None)
                user_cd.set_extra_data(extra_data)
                await self.db.ext.update_user_cd(user_cd)
            else:
                current_hp = base_hp + int((max_hp - base_hp) * elapsed / 600)
                current_hp = min(max_hp, max(1, current_hp))

        if current_hp != player.hp:
            player.hp = current_hp
            await self.db.update_player(player)

        return current_hp, max_hp, recovery_enabled, cooldown_remaining

    async def _resolve_display_battle_hp_unified(self, player: Player):
        """Resolve current battle HP via the shared recovery utility."""
        impart_info = await self.db.ext.get_impart_info(player.user_id)
        hp_buff = impart_info.impart_hp_per if impart_info else 0.0
        max_hp = int(player.experience * (1 + hp_buff) // 2)
        if max_hp <= 0:
            return player.hp, 0, False, 0

        current_hp = max(1, min(player.hp, max_hp)) if player.hp > 0 else max_hp
        user_cd = await self.db.ext.get_user_cd(player.user_id)
        if not user_cd:
            if current_hp != player.hp:
                player.hp = current_hp
                await self.db.update_player(player)
            return current_hp, max_hp, False, 0

        current_hp, recovery_enabled, cooldown_remaining, resolved_extra_data, changed = resolve_boss_battle_hp_state(
            current_hp,
            max_hp,
            user_cd.get_extra_data(),
        )

        if changed:
            user_cd.set_extra_data(resolved_extra_data)
            await self.db.ext.update_user_cd(user_cd)

        if current_hp != player.hp:
            player.hp = current_hp
            await self.db.update_player(player)

        return current_hp, max_hp, recovery_enabled, cooldown_remaining

    async def _resolve_display_status(self, player: Player) -> str:
        """Resolve the player status shown in /我的信息."""
        user_cd = await self.db.ext.get_user_cd(player.user_id)
        if user_cd and user_cd.type != UserStatus.IDLE:
            return UserStatus.get_name(user_cd.type)
        return player.state or "空闲"

    async def handle_start_xiuxian(self, event: AstrMessageEvent, cultivation_type: str = ""):
        """处理创建角色。"""
        user_id = event.get_sender_id()

        if await self.db.get_player_by_id(user_id):
            yield event.plain_result("道友，你已踏入仙途，无需重复创建角色。")
            return

        cultivation_type = cultivation_type.strip()
        if not cultivation_type:
            help_msg = (
                "欢迎踏入修仙之路\n"
                "━━━━━━━━━━\n"
                "请选择你的修炼方式：\n\n"
                "【灵修】以灵气为主，擅长法术\n"
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
            "━━━━━━━━━━\n"
            f"修炼方式：{new_player.cultivation_type}\n"
            f"灵根：{new_player.spiritual_root}\n"
            f"评价：{root_description}\n"
            f"启动资金：{new_player.gold} 灵石\n"
            "━━━━━━━━━━\n"
            f"发送“{CMD_PLAYER_INFO}”查看当前状态"
        )
        yield event.plain_result(reply_msg)

    @player_required
    async def handle_player_info(self, player: Player, event: AstrMessageEvent):
        """查看玩家信息。"""
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

        battle_hp, battle_hp_max, hp_recovering, boss_cooldown_remaining = await self._resolve_display_battle_hp_unified(player)
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

        reply_msg = (
            f"📋 道友 {dao_hao} 的信息\n"
            "━━━━━━━━━━━━━━━\n"
            "【基本信息】\n"
            f"  道号：{dao_hao}\n"
            f"  境界：{player.get_level(self.config_manager)}\n"
            f"  修为：{int(player.experience):,}/{int(required_exp):,}\n"
            f"  灵石：{player.gold:,}\n"
            f"  战力：{combat_power:,}\n"
            f"  灵根：{player.spiritual_root}\n"
            f"  突破加成：{breakthrough_rate}\n"
            "\n"
            "【修炼属性】\n"
            f"  修炼方式：{player.cultivation_type}\n"
            f"  状态：{display_status}\n"
            f"  寿命：{player.lifespan}\n"
            f"  精神力：{total_attrs['mental_power']}\n"
            f"  战斗HP：{battle_hp}/{battle_hp_max}\n"
        )

        if hp_recovering:
            if boss_cooldown_remaining > 0:
                minutes = boss_cooldown_remaining // 60
                seconds = boss_cooldown_remaining % 60
                reply_msg += f"  Boss冷却：{minutes}分{seconds}秒\n"
            reply_msg += "  战斗HP恢复：每分钟恢复10%，约10分钟恢复满血\n"

        if player.cultivation_type == "体修":
            reply_msg += (
                f"  气血：{player.blood_qi}/{total_attrs.get('max_blood_qi', 0)}\n"
                f"  物伤：{total_attrs['physical_damage']}\n"
                f"  法伤：{total_attrs['magic_damage']}\n"
                f"  物防：{total_attrs['physical_defense']}\n"
                f"  法防：{total_attrs['magic_defense']}\n"
            )
        else:
            reply_msg += (
                f"  灵气：{player.spiritual_qi}/{total_attrs.get('max_spiritual_qi', 0)}\n"
                f"  法伤：{total_attrs['magic_damage']}\n"
                f"  物伤：{total_attrs['physical_damage']}\n"
                f"  法防：{total_attrs['magic_defense']}\n"
                f"  物防：{total_attrs['physical_defense']}\n"
            )

        reply_msg += (
            "\n"
            "【装备信息】\n"
            f"  主修功法：{technique_name}\n"
            f"  法器：{weapon_name}\n"
            f"  防具：{armor_name}\n"
            "\n"
            "【宗门信息】\n"
            f"  所在宗门：{sect_name}\n"
            f"  宗门职位：{position_name}\n"
        )

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

            reply_msg += (
                "\n"
                "【贷款信息】\n"
                f"  类型：{loan_type_name}\n"
                f"  应还：{total_due:,} 灵石\n"
                f"  剩余：{time_str}\n"
                "  逾期将被追杀致死\n"
            )

        reply_msg += "━━━━━━━━━━━━━━━"
        yield event.plain_result(reply_msg)

    @player_required
    async def handle_start_cultivation(self, player: Player, event: AstrMessageEvent):
        """开始闭关。"""
        if player.state == "修炼中":
            yield event.plain_result("道友已在闭关中，请勿重复进入。")
            return

        user_cd = await self.db.ext.get_user_cd(player.user_id)
        if user_cd and user_cd.type != UserStatus.IDLE:
            current_status = UserStatus.get_name(user_cd.type)
            yield event.plain_result(f"❌ 道友当前正{current_status}，无法闭关修炼！")
            return

        player.state = "修炼中"
        player.cultivation_start_time = int(time.time())
        await self.db.update_player(player)
        await self.db.ext.set_user_busy(player.user_id, UserStatus.CULTIVATING, 0)

        yield event.plain_result(
            "🧘 道友已进入闭关状态\n"
            "━━━━━━━━━━\n"
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
            "🪷 道友出关成功\n"
            "━━━━━━━━━━\n"
            f"闭关时长：{time_str}\n"
            f"获得修为：{gained_exp:,}{exceed_msg}\n"
            f"当前修为：{player.experience:,}\n"
            "━━━━━━━━━━\n"
            "道友已回归红尘，可继续修行。"
        )
        reply_msg += enlightenment_msg
        yield event.plain_result(reply_msg)

    @player_required
    async def handle_check_in(self, player: Player, event: AstrMessageEvent):
        """每日签到。"""
        today = datetime.now().strftime("%Y-%m-%d")
        if player.last_check_in_date == today:
            yield event.plain_result("📅 道友今日已经签到过了，请明日再来。")
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
            "━━━━━━━━━━\n"
            f"获得灵石：{check_in_gold}\n"
            f"当前灵石：{player.gold}\n"
            "━━━━━━━━━━\n"
            "明日再来，莫要忘记。"
        )
        yield event.plain_result(reply_msg)

    @player_required
    async def handle_rebirth(self, player: Player, event: AstrMessageEvent, confirm_text: str = ""):
        """弃道重修。"""
        user_cd = await self.db.ext.get_user_cd(player.user_id)
        if user_cd and user_cd.type != UserStatus.IDLE:
            status_name = UserStatus.get_name(user_cd.type)
            yield event.plain_result(f"❌ 你当前正在「{status_name}」，无法弃道重修。")
            return

        if player.state != "空闲":
            yield event.plain_result("❌ 只有处于空闲状态时才能弃道重修，请先结束其他活动。")
            return

        loan = await self.db.ext.get_active_loan(player.user_id)
        if loan:
            yield event.plain_result("❌ 你仍有未结清的灵石贷款，无法重修，请先还款。")
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
                    "⏳ 弃道重修冷却中\n"
                    "━━━━━━━━━━\n"
                    f"距离下次重修还需：{days}天{hours}小时{minutes}分钟"
                )
                return

        if confirm_text.strip() != "确认":
            yield event.plain_result(
                "⚠️ 弃道重修将删除当前角色的所有数据，且无法撤回。\n"
                "限制：每7天只能重修一次，且必须处于空闲状态、无贷款时使用。\n"
                "━━━━━━━━━━\n"
                "若你已做好准备，请发送：\n"
                "弃道重修 确认"
            )
            return

        await self.db.delete_player_cascade(player.user_id)
        await self.db.ext.set_system_config(key, str(now))

        yield event.plain_result(
            "💀 你选择了弃道重修，旧生一切化为尘埃。\n"
            "━━━━━━━━━━\n"
            "可立即使用“我要修仙”重新踏上仙途。\n"
            "7天内不可再次重修。"
        )

    @player_required
    async def handle_reroll_root(self, player: Player, event: AstrMessageEvent):
        """逆天改命：花费灵石重置灵根。"""
        user_cd = await self.db.ext.get_user_cd(player.user_id)
        if user_cd and user_cd.type != UserStatus.IDLE:
            status_name = UserStatus.get_name(user_cd.type)
            yield event.plain_result(f"❌ 你当前正在「{status_name}」，无法逆天改命。")
            return

        if player.state != "空闲":
            yield event.plain_result("❌ 只有处于空闲状态时才能逆天改命，请先结束其他活动。")
            return

        if player.gold < REROLL_ROOT_COST:
            yield event.plain_result(
                "❌ 灵石不足\n"
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
            result_emoji = "🎉"
            result_text = "天命改写，灵根蜕变！"
        elif new_quality < old_quality:
            result_emoji = "😅"
            result_text = "造化弄人，灵根退化了。"
        else:
            result_emoji = "😐"
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
        """为逆天改命结果提供简单的灵根品级比较。"""
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
