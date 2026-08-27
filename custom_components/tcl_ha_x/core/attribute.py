"""TCL 设备物模型属性解析器。

核心原则：
1. 同一个物理属性不能同时由 climate 和普通实体控制，避免 HA 中出现重复实体。
2. 只读状态属性必须解析为 sensor，不能因为类型是 bool 就被误判为 switch。
3. 对云端返回的缺失字段做默认值兜底，避免单个字段缺省导致解析中断。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.switch import SwitchDeviceClass
from homeassistant.const import Platform

from ..helpers import ATTR_NAME

_LOGGER = logging.getLogger(__name__)


# 这些属性已经由主 climate 实体统一暴露，普通实体不再重复生成。
CLIMATE_MANAGED_KEYS = {
    "powerSwitch",
    "workMode",
    "targetTemperature",
    "currentTemperature",
    "windSpeedAutoSwitch",
}


# 已知只读属性。它们反映设备状态，不能被反向控制。
READONLY_SENSOR_KEYS = {
    "currentTemperature",
    "filterAgePercentage",
    "lightSenseStatus",
    "selfCleanStatus",
    "sleepTime",
    "verticalWind",
    "horizontalWind",
    "windSpeed7Gear",
    "PTCStatus",
    "internalUnitCoilTemperature",
    "externalUnitCoilTemperature",
    "externalUnitTemperature",
    "externalUnitExhaustTemperature",
    "internalUnitFanSpeed",
    "externalUnitFanSpeed",
    "externalUnitFanGear",
    "compressorFrequency",
    "externalUnitElectricCurrent",
    "externalUnitVoltage",
    "fourWayValveStatus",
    "expansionValve",
    "expansionValve ",
    "errorCode",
    "aiSmartControlSource",
    "tslLatestVersion",
    "tslReqVersion",
    "tslQueryTime",
}


# 由 climate 主实体覆盖后仍保留为独立 switch 的高级控制属性。
CONTROL_SWITCH_KEYS = {
    "softWind",
    "ECO",
    "PTC",
    "beepSwitch",
    "screen",
    "antiMoldew",
    "selfLearn",
    "selfClean",
    "blueLightSwitch",
    "lightSense",
    "newWindSwitch",
    "newWindECOSwitch",
    "newWindAutoSwitch",
    "purifyDeodorizeSwitch",
}


# climate 不直接覆盖的下拉选择属性。
CONTROL_SELECT_KEYS = {
    "sleep",
    "verticalDirection",
    "horizontalDirection",
}


# climate 只提供自动/手动风模式，百分比风速保留为独立 number 以支持精确控制。
CONTROL_NUMBER_KEYS = {
    "windSpeedPercentage",
    "newWindPercentage",
    "roomSize",
}


# 以这些后缀结尾的 bool 属性优先视为只读状态，避免 lightSenseStatus 被误判为开关。
READONLY_BOOL_SUFFIXES = ("status", "state")


class TclAttribute:
    """描述一个 TCL 物模型属性以及它应该映射到的 HA 平台。"""

    def __init__(
        self,
        key: str,
        display_name: str,
        platform: Platform,
        options: dict | None = None,
        ext: dict | None = None,
    ) -> None:
        self._key = key
        self._display_name = display_name
        self._platform = platform
        self._options = options if options is not None else {}
        self._ext = ext if ext is not None else {}

    @property
    def key(self) -> str:
        return self._key

    @property
    def display_name(self) -> str:
        return self._display_name

    @property
    def platform(self) -> Platform:
        return self._platform

    @property
    def options(self) -> dict:
        return self._options

    @property
    def ext(self) -> dict:
        return self._ext


class TclAttributeParser(ABC):
    """物模型属性解析器抽象接口。"""

    @abstractmethod
    def parse_attribute(self, attribute: dict) -> TclAttribute | None:
        """把云端物模型属性转换为 TclAttribute；不支持的属性返回 None。"""


class V1SpecAttributeParser(TclAttributeParser):
    """TCL v1 物模型属性解析器。"""

    def parse_attribute(self, attribute: dict) -> TclAttribute | None:
        identifier = attribute.get("identifier")
        if not identifier:
            _LOGGER.debug("忽略缺少 identifier 的物模型属性: %s", attribute)
            return None

        data_type = attribute.get("type") or ""

        # 主 climate 实体已经覆盖的属性，不再创建独立实体。
        if identifier in CLIMATE_MANAGED_KEYS:
            return None

        # 只读状态优先解析为 sensor。
        if identifier in READONLY_SENSOR_KEYS or identifier.lower().endswith(
            READONLY_BOOL_SUFFIXES
        ):
            return self._parse_as_status_sensor(attribute)

        if identifier in CONTROL_SWITCH_KEYS or "bool" in data_type:
            return self._parse_as_switch(attribute)

        if identifier in CONTROL_SELECT_KEYS or "enum" in data_type:
            return self._parse_as_select(attribute)

        if identifier in CONTROL_NUMBER_KEYS or any(
            kind in data_type for kind in ("int", "double", "float")
        ):
            return self._parse_as_number(attribute)

        if "struct" in data_type:
            return self._parse_as_struct_sensor(attribute)

        _LOGGER.debug(
            "无法识别的物模型属性，identifier=%s, type=%s",
            identifier,
            data_type,
        )
        return None

    @staticmethod
    def _parse_as_switch(attribute: dict) -> TclAttribute:
        identifier = attribute["identifier"]
        return TclAttribute(
            identifier,
            ATTR_NAME.get(identifier, attribute.get("title") or identifier),
            Platform.SWITCH,
            {"device_class": SwitchDeviceClass.SWITCH},
        )

    @staticmethod
    def _parse_as_select(attribute: dict) -> TclAttribute:
        identifier = attribute["identifier"]
        specs = attribute.get("specs") or {}
        value_comparison_table = {
            str(key): value for key, value in specs.items()
        }
        return TclAttribute(
            identifier,
            ATTR_NAME.get(identifier, attribute.get("title") or identifier),
            Platform.SELECT,
            {"options": list(value_comparison_table.values())},
            {"value_comparison_table": value_comparison_table},
        )

    @staticmethod
    def _parse_as_number(attribute: dict) -> TclAttribute:
        identifier = attribute["identifier"]
        specs = attribute.get("specs") or {}
        options = {
            "native_min_value": float(specs.get("min", 0)),
            "native_max_value": float(specs.get("max", 100)),
            "native_step": float(specs.get("step", 1)),
        }
        unit = specs.get("unit")
        if unit:
            options["native_unit_of_measurement"] = unit
        return TclAttribute(
            identifier,
            ATTR_NAME.get(identifier, attribute.get("title") or identifier),
            Platform.NUMBER,
            options,
        )

    @staticmethod
    def _parse_as_status_sensor(attribute: dict) -> TclAttribute:
        identifier = attribute["identifier"]
        data_type = attribute.get("type") or ""
        specs = attribute.get("specs") or {}

        # bool 状态统一翻译成“关闭/开启”，并对云端可能返回的不同字面量做兼容。
        if "bool" in data_type:
            options = [specs.get("0", "关闭"), specs.get("1", "开启")]
            value_comparison_table = {}
            for raw in (0, "0", False, "False", "false", "off", "OFF"):
                value_comparison_table[str(raw)] = options[0]
            for raw in (1, "1", True, "True", "true", "on", "ON"):
                value_comparison_table[str(raw)] = options[1]
            return TclAttribute(
                identifier,
                ATTR_NAME.get(identifier, attribute.get("title") or identifier),
                Platform.SENSOR,
                {
                    "device_class": SensorDeviceClass.ENUM,
                    "options": options,
                },
                {
                    "sensor_type": "simple",
                    "value_comparison_table": value_comparison_table,
                    "bool_status": True,
                },
            )

        return V1SpecAttributeParser._parse_as_simple_sensor(attribute)

    @staticmethod
    def _parse_as_simple_sensor(attribute: dict) -> TclAttribute:
        identifier = attribute["identifier"]
        data_type = attribute.get("type") or ""
        specs = attribute.get("specs") or {}
        options = {}
        ext = {"sensor_type": "simple"}

        if "enum" in data_type or "bool" in data_type:
            if "bool" in data_type:
                option_values = [specs.get("0", "关闭"), specs.get("1", "开启")]
                value_comparison_table = {
                    str(raw): option_values[1]
                    for raw in (1, "1", True, "True", "true", "on", "ON")
                }
                value_comparison_table.update(
                    {
                        str(raw): option_values[0]
                        for raw in (0, "0", False, "False", "false", "off", "OFF")
                    }
                )
            else:
                option_values = list(specs.values())
                value_comparison_table = {
                    str(key): value for key, value in specs.items()
                }
            options = {
                "device_class": SensorDeviceClass.ENUM,
                "options": option_values,
            }
            ext["value_comparison_table"] = value_comparison_table
        elif "int" in data_type or "double" in data_type or "float" in data_type:
            unit = specs.get("unit")
            if unit:
                options["native_unit_of_measurement"] = unit
            ext["unit"] = unit or ""

        return TclAttribute(
            identifier,
            ATTR_NAME.get(identifier, attribute.get("title") or identifier),
            Platform.SENSOR,
            options,
            ext,
        )

    @staticmethod
    def _parse_as_struct_sensor(attribute: dict) -> TclAttribute:
        identifier = attribute["identifier"]
        specs = attribute.get("specs") or []
        options = {}
        ext = {
            "struct_info": {
                "title": attribute.get("title") or identifier,
                "description": attribute.get("description") or "",
                "function": attribute.get("function") or "",
            }
        }

        for item in specs:
            if not isinstance(item, dict):
                continue
            data_type = item.get("dataType") or {}
            data_id = item.get("identifier")
            if not data_id:
                continue
            field_ext = {"name": item.get("name") or data_id}
            field_options = {}
            field_table = {}

            type_name = data_type.get("type") or ""
            field_specs = data_type.get("specs") or {}

            if "enum" in type_name:
                field_table = {
                    str(key): value for key, value in field_specs.items()
                }
                field_options["device_class"] = SensorDeviceClass.ENUM
                field_options["options"] = list(field_table.values())
                field_ext["value_comparison_table"] = field_table
            elif "int" in type_name or "double" in type_name or "float" in type_name:
                field_options = {
                    "native_min_value": float(field_specs.get("min", 0)),
                    "native_max_value": float(field_specs.get("max", 100)),
                    "native_step": float(field_specs.get("step", 1)),
                }
                unit = field_specs.get("unit")
                if unit:
                    field_options["native_unit_of_measurement"] = unit
                    field_ext["unit"] = unit
                    if field_specs.get("unitName"):
                        field_ext["unit_name"] = field_specs["unitName"]

            if "mappingType" in data_type:
                field_ext["mapping_type"] = data_type["mappingType"]

            options[data_id] = field_options
            ext[data_id] = field_ext

        return TclAttribute(
            identifier,
            ATTR_NAME.get(identifier, attribute.get("title") or identifier),
            Platform.SENSOR,
            options,
            ext,
        )
