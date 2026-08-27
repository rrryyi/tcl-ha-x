import logging
from typing import Any

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ClimateEntityFeature,
    HVACMode,
    HVACAction,
    SWING_OFF,
    SWING_BOTH,
    SWING_VERTICAL,
    SWING_HORIZONTAL,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature, Platform
from homeassistant.core import HomeAssistant

from ..core.attribute import TclAttribute
from ..core.device import TclDevice
from ..const import DOMAIN
from ..entity import TclAbstractEntity

_LOGGER = logging.getLogger(__name__)

MODE_MAP = {
    "auto": HVACMode.AUTO,
    "cool": HVACMode.COOL,
    "dry": HVACMode.DRY,
    "fan_only": HVACMode.FAN_ONLY,
    "heat": HVACMode.HEAT,
}

WORK_MODE_TO_HVAC = {
    0: HVACMode.AUTO,
    1: HVACMode.COOL,
    2: HVACMode.DRY,
    3: HVACMode.FAN_ONLY,
    4: HVACMode.HEAT,
    5: HVACMode.AUTO,
}

HVAC_TO_WORK_MODE = {
    HVACMode.AUTO: 0,
    HVACMode.COOL: 1,
    HVACMode.DRY: 2,
    HVACMode.FAN_ONLY: 3,
    HVACMode.HEAT: 4,
}


# 新增风扇模式与风速百分比的映射
FAN_SPEED_MAP = {
    "自动": 0,
    "低": 20,
    "中低": 25,
    "中": 50,
    "高": 75,
    "全速": 100,
}

# 反向映射，用于从设备返回的百分比查找对应的模式名称
REVERSE_FAN_SPEED_MAP = {v: k for k, v in FAN_SPEED_MAP.items()}


def _as_int(value: Any, default: int = 0) -> int:
    """把云端可能返回的 int/float/str/bool 安全转换为 int。"""
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float | None = None) -> float | None:
    """把云端可能返回的数值安全转换为 float。"""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _is_power_off(value: Any) -> bool:
    """判断电源开关是否处于关闭状态，兼容 bool/int/str 表示。"""
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return value == 0
    return str(value).strip().lower() in {"0", "off", "false", "关"}


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities) -> None:
    """设置 TCL 空调实体"""
    devices = hass.data[DOMAIN]["devices"]

    entities = []
    for device in devices:
        # 使用设备类别判断空调，而不是依赖已过滤掉的 climate 托管属性。
        if device.is_ac:
            # 为该空调设备创建一个"虚拟"的 TclAttribute，用于兼容 TclAbstractEntity 的构造函数
            climate_attr = TclAttribute(
                key="climate_control",  # 为气候实体定义一个通用 key
                display_name=f"{device.name} 空调",  # 气候实体显示名称
                platform=Platform.CLIMATE  # 指定平台为 Climate
            )
            entities.append(TclClimateEntity(device, climate_attr))

    async_add_entities(entities)


class TclClimateEntity(TclAbstractEntity, ClimateEntity):
    """TCL 空调实体"""

    # 初始化支持的特性，温度单位和 HVAC 模式
    _attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.FAN_MODE
            | ClimateEntityFeature.SWING_MODE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
    )
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = 16
    _attr_max_temp = 31
    _attr_target_temperature_step = 0.5
    _attr_fan_modes = list(FAN_SPEED_MAP.keys())
    _attr_hvac_modes = [HVACMode.OFF] + list(MODE_MAP.values())

    def __init__(self, device: TclDevice, attribute: TclAttribute):
        """初始化空调实体。"""
        # 调用 TclAbstractEntity 的构造函数，它会处理 unique_id、name、device_info 以及事件监听
        super().__init__(device, attribute)

        # 初始化记忆模式，默认给个自动，防止第一次无数据。
        self._last_on_mode = HVACMode.AUTO

    def _update_value(self) -> None:
        """从设备属性数据中更新实体状态。"""
        power = self._device.attribute_snapshot_data.get("powerSwitch")
        if power is None:
            self._attr_available = False
            return

        self._attr_available = True

        if _is_power_off(power):
            self._attr_hvac_mode = HVACMode.OFF
        else:
            mode = _as_int(
                self._device.attribute_snapshot_data.get("workMode"),
                0,
            )
            self._attr_hvac_mode = WORK_MODE_TO_HVAC.get(mode, HVACMode.AUTO)
            # 只要不是关机，就实时记录当前模式到记忆变量。
            self._last_on_mode = self._attr_hvac_mode

        if self._attr_hvac_mode == HVACMode.HEAT:
            self._attr_hvac_action = HVACAction.HEATING
        elif self._attr_hvac_mode == HVACMode.COOL:
            self._attr_hvac_action = HVACAction.COOLING
        elif self._attr_hvac_mode == HVACMode.DRY:
            self._attr_hvac_action = HVACAction.DRYING
        elif self._attr_hvac_mode == HVACMode.FAN_ONLY:
            self._attr_hvac_action = HVACAction.FAN
        elif self._attr_hvac_mode == HVACMode.AUTO:
            self._attr_hvac_action = HVACAction.IDLE
        elif self._attr_hvac_mode == HVACMode.OFF:
            self._attr_hvac_action = HVACAction.OFF
        else:
            self._attr_hvac_action = HVACAction.IDLE

        target = _as_float(
            self._device.attribute_snapshot_data.get("targetTemperature")
        )
        self._attr_target_temperature = target

        self._attr_current_temperature = _as_float(
            self._device.attribute_snapshot_data.get("currentTemperature")
        )

        wind_speed_percentage = self._device.attribute_snapshot_data.get("windSpeedPercentage")
        if wind_speed_percentage is not None:
            wind_speed = _as_float(wind_speed_percentage, 0)
            closest_speed = min(
                FAN_SPEED_MAP.values(),
                key=lambda x: abs(x - wind_speed),
            )
            self._attr_fan_mode = REVERSE_FAN_SPEED_MAP.get(closest_speed, "自动")
        else:
            self._attr_fan_mode = "自动"

        vertical_on = _as_int(
            self._device.attribute_snapshot_data.get("verticalWind")
        ) == 1
        horizontal_on = _as_int(
            self._device.attribute_snapshot_data.get("horizontalWind")
        ) == 1

        if vertical_on and horizontal_on:
            self._attr_swing_mode = SWING_BOTH
        elif vertical_on:
            self._attr_swing_mode = SWING_VERTICAL
        elif horizontal_on:
            self._attr_swing_mode = SWING_HORIZONTAL
        else:
            self._attr_swing_mode = SWING_OFF

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """设置 HVAC 模式。"""
        if hvac_mode == HVACMode.OFF:
            self._send_command({"powerSwitch": 0})
            return

        if _is_power_off(
            self._device.attribute_snapshot_data.get("powerSwitch")
        ):
            self._send_command({"powerSwitch": 1})

        work_mode = HVAC_TO_WORK_MODE.get(hvac_mode, 0)
        self._send_command({"workMode": work_mode})

    async def async_turn_on(self):
        """Turn the entity on."""
        target_mode = self._last_on_mode
        if target_mode == HVACMode.OFF:
            target_mode = HVACMode.AUTO
        await self.async_set_hvac_mode(target_mode)

    async def async_turn_off(self):
        """Turn the entity off."""
        if self._attr_hvac_mode != HVACMode.OFF:
            self._last_on_mode = self._attr_hvac_mode
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """设置风扇模式。"""
        target_speed = FAN_SPEED_MAP.get(fan_mode)
        if target_speed is not None:
            self._send_command({"windSpeedPercentage": target_speed})
        else:
            _LOGGER.warning(f"无法识别的风扇模式: {fan_mode}")

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """设置目标温度。"""
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is not None:
            self._send_command({"targetTemperature": temp})

    @property
    def swing_modes(self):
        """摆动列表"""
        return [SWING_OFF, SWING_BOTH, SWING_VERTICAL, SWING_HORIZONTAL]

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """设置摆动"""
        if swing_mode == SWING_OFF:
            self._send_command({"verticalWind": 0, "horizontalWind": 0})
        elif swing_mode == SWING_BOTH:
            self._send_command({"verticalWind": 1, 'verticalDirection': 1, "horizontalWind": 1, 'horizontalDirection': 1})
        elif swing_mode == SWING_VERTICAL:
            self._send_command({"verticalWind": 1, 'verticalDirection': 1, "horizontalWind": 0})
        elif swing_mode == SWING_HORIZONTAL:
            self._send_command({"verticalWind": 0, "horizontalWind": 1, 'horizontalDirection': 1})
