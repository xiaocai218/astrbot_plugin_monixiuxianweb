import time
from typing import Any, Dict, Tuple


BOSS_CHALLENGE_COOLDOWN_KEY = "boss_challenge_cd_until"
BOSS_CHALLENGE_RECOVERY_KEY = "boss_challenge_hp_recovering"
BOSS_CHALLENGE_RECOVERY_BASE_HP_KEY = "boss_challenge_hp_recovery_base_hp"
BOSS_CHALLENGE_RECOVERY_STARTED_AT_KEY = "boss_challenge_hp_recovery_started_at"
BOSS_CHALLENGE_COOLDOWN_SECONDS = 300
BOSS_CHALLENGE_RECOVERY_SECONDS = 600


def calculate_recovering_boss_hp(base_hp: int, max_hp: int, started_at: int, now: int | None = None) -> Tuple[int, bool]:
    """Recover 10% of max HP per minute, fully recovered after 10 minutes."""
    if max_hp <= 1 or base_hp >= max_hp:
        return max_hp, True

    current_time = int(now if now is not None else time.time())
    elapsed = max(0, current_time - int(started_at))
    if elapsed >= BOSS_CHALLENGE_RECOVERY_SECONDS:
        return max_hp, True

    recovered_hp = base_hp + int((max_hp - base_hp) * elapsed / BOSS_CHALLENGE_RECOVERY_SECONDS)
    return min(max_hp, max(1, recovered_hp)), recovered_hp >= max_hp


def resolve_boss_battle_hp_state(
    current_hp: int,
    max_hp: int,
    extra_data: Dict[str, Any] | None,
    now: int | None = None,
) -> Tuple[int, bool, int, Dict[str, Any], bool]:
    """
    Resolve current Boss battle HP from saved recovery anchors.

    Returns:
        hp,
        recovery_enabled,
        cooldown_remaining,
        updated_extra_data,
        extra_data_changed
    """
    if max_hp <= 0:
        return current_hp, False, 0, dict(extra_data or {}), False

    current_time = int(now if now is not None else time.time())
    normalized_hp = max(1, min(int(current_hp), max_hp)) if int(current_hp) > 0 else max_hp
    resolved_extra_data: Dict[str, Any] = dict(extra_data or {})
    changed = False

    cooldown_until = int(resolved_extra_data.get(BOSS_CHALLENGE_COOLDOWN_KEY, 0) or 0)
    cooldown_remaining = max(0, cooldown_until - current_time) if cooldown_until else 0
    recovery_enabled = bool(resolved_extra_data.get(BOSS_CHALLENGE_RECOVERY_KEY, 0))

    # 兼容旧数据或异常中断场景：只要当前战斗 HP 低于上限，就自动补建恢复锚点。
    if not recovery_enabled and normalized_hp < max_hp:
        started_at = max(0, cooldown_until - BOSS_CHALLENGE_COOLDOWN_SECONDS) if cooldown_until else current_time
        resolved_extra_data[BOSS_CHALLENGE_RECOVERY_KEY] = 1
        resolved_extra_data[BOSS_CHALLENGE_RECOVERY_BASE_HP_KEY] = normalized_hp
        resolved_extra_data[BOSS_CHALLENGE_RECOVERY_STARTED_AT_KEY] = started_at
        recovery_enabled = True
        changed = True

    if recovery_enabled:
        base_hp = int(resolved_extra_data.get(BOSS_CHALLENGE_RECOVERY_BASE_HP_KEY, 0) or 0)
        started_at = int(resolved_extra_data.get(BOSS_CHALLENGE_RECOVERY_STARTED_AT_KEY, 0) or 0)

        if base_hp <= 0:
            base_hp = normalized_hp if normalized_hp > 0 else 1
            resolved_extra_data[BOSS_CHALLENGE_RECOVERY_BASE_HP_KEY] = base_hp
            changed = True
        if started_at <= 0:
            started_at = max(0, cooldown_until - BOSS_CHALLENGE_COOLDOWN_SECONDS) if cooldown_until else current_time
            resolved_extra_data[BOSS_CHALLENGE_RECOVERY_STARTED_AT_KEY] = started_at
            changed = True

        normalized_hp, fully_recovered = calculate_recovering_boss_hp(base_hp, max_hp, started_at, current_time)
        if fully_recovered:
            resolved_extra_data.pop(BOSS_CHALLENGE_RECOVERY_KEY, None)
            resolved_extra_data.pop(BOSS_CHALLENGE_RECOVERY_BASE_HP_KEY, None)
            resolved_extra_data.pop(BOSS_CHALLENGE_RECOVERY_STARTED_AT_KEY, None)
            recovery_enabled = False
            changed = True

    return normalized_hp, recovery_enabled, cooldown_remaining, resolved_extra_data, changed
