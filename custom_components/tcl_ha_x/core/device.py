import json
import logging
from typing import List

from .attribute import TclAttribute, V1SpecAttributeParser

_LOGGER = logging.getLogger(__name__)


class TclDevice:
    _raw_data: dict
    _attributes: List[TclAttribute]
    _attribute_snapshot_data: dict

    def __init__(self, client, raw: dict):
        self._client = client
        self._raw_data = raw
        self._attributes = []
        self._attribute_snapshot_data = {}

    @property
    def id(self):
        return self._raw_data['deviceId']

    @property
    def name(self):
        nick_name = self._raw_data.get('nickName')
        return nick_name or self.id

    @property
    def type(self):
        return self._raw_data.get('category')

    @property
    def is_ac(self) -> bool:
        """判断设备是否为空调，兼容不同大小写和命名。"""
        category = str(self.type or '').strip().lower()
        return category in {
            'ac',
            'airconditioner',
            'air_conditioner',
            'air-conditioner',
            '空调',
        }

    @property
    def product_key(self):
        return self._raw_data.get('productKey')

    @property
    def is_online(self):
        return self._raw_data.get('isOnline')

    @property
    def is_control(self):
        return self._raw_data.get('weChatControl')

    @property
    def attributes(self) -> List[TclAttribute]:
        return self._attributes

    @property
    def attribute_snapshot_data(self) -> dict:
        return self._attribute_snapshot_data

    @property
    def getClient(self):
        return self._client

    def update_attribute_snapshot_data(self, new_data: dict):
        # 可以在这里添加数据验证逻辑
        self._attribute_snapshot_data = new_data

    async def async_init(self):
        # 解析Attribute
        # noinspection PyBroadException
        try:
            parser = V1SpecAttributeParser()
            attributes = await self._client.get_digital_model_from_cache(self)

            _LOGGER.info(
                'Device %s (productKey=%s) got %d raw attributes',
                self.id, self.product_key, len(attributes) if attributes else 0
            )

            for item in (attributes or []):
                try:
                    attr = parser.parse_attribute(item)
                    if attr:
                        self._attributes.append(attr)
                        _LOGGER.info(
                            'Device %s parsed: key=%s -> platform=%s',
                            self.id, attr.key, attr.platform
                        )
                    else:
                        _LOGGER.warning(
                            'Device %s attribute %s (type=%s) returned None',
                            self.id, item.get('identifier'), item.get('type')
                        )
                except Exception:
                    _LOGGER.exception(
                        "Tcl device %s attribute %s parsing error occurred",
                        self.id, item.get('name', item.get('identifier', 'unknown'))
                    )

            snapshot_data = await self._client.get_device_snapshot_data(self.id)
            _LOGGER.debug(
                'device %s snapshot data fetch successful. data: %s',
                self.id,
                json.dumps(snapshot_data)
            )
            self._attribute_snapshot_data = snapshot_data
        except Exception:
            _LOGGER.exception('Tcl device %s init failed', self.id)

    def __str__(self) -> str:
        return json.dumps({
            'id': self.id,
            'name': self.name,
            'type': self.type,
            'product_key': self.product_key,
            'is_online': self.is_online,
            'is_control': self.is_control
        })
