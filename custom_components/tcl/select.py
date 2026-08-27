import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from . import async_register_entity
from .core.attribute import TclAttribute
from .core.device import TclDevice
from .entity import TclAbstractEntity
from .helpers import get_key_by_value

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    await async_register_entity(
        hass,
        entry,
        async_add_entities,
        Platform.SELECT,
        lambda device, attribute: TclSelect(device, attribute)
    )


class TclSelect(TclAbstractEntity, SelectEntity):

    def __init__(self, device: TclDevice, attribute: TclAttribute):
        super().__init__(device, attribute)

        if 'value_comparison_table' not in attribute.ext.keys():
            raise ValueError('value_comparison_table must exist')

    def _update_value(self):
        if self._attribute.key not in self._attributes_data:
            self._attr_available = False
            return
        self._attr_available = True
        self._attr_current_option = self._get_value_from_comparison_table(
            self._attributes_data[self._attribute.key]
        )

    def select_option(self, option: str) -> None:
        # 这里需要通过 option 反查原始 key。
        # 必须使用 `is not None`，否则 key == 0 时会被误判为 False。
        key = get_key_by_value(self._attribute.ext.get('value_comparison_table'), option)
        if key is not None:
            self._send_command({
                self._attribute.key: key
            })

    def _get_value_from_comparison_table(self, value):
        value_comparison_table = self._attribute.ext.get('value_comparison_table', {})
        if str(value) not in value_comparison_table:
            _LOGGER.warning('Device [{}] attribute [{}] value [{}] not recognizable'.format(
                self._device.id, self._attribute.key, value
            ))
            return value

        return value_comparison_table.get(str(value))
