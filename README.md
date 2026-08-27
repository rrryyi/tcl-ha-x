# TCL 空调 Home Assistant 集成

本集成以 [ndwzy/tcl-ha](https://github.com/ndwzy/tcl-ha) 为基础，并参考
[qwqqq6/tclplus-ac](https://github.com/qwqqq6/tclplus-ac) 的国内 TCL+ 属性和
控制规则做了增强，目标是减少重复实体，并让只读状态属性不再被误判成开关。

## 主要改进

- `climate` 实体统一管理电源、模式、目标温度、当前温度、自动风、扫风。
- `powerSwitch`、`workMode`、`targetTemperature`、`currentTemperature`、
  `windSpeedAutoSwitch` 不再重复生成普通实体。
- `lightSenseStatus`、`selfCleanStatus`、`PTCStatus`、`verticalWind`、
  `horizontalWind` 等只读状态统一映射为 `sensor`，避免出现假开关。
- 修复 `select` 选项值为 `0` 时不发送命令的问题。
- 修复 `climate.workMode` 只按字符串匹配，数字模式无法正确显示的问题。
- 补充更完整的诊断传感器命名和属性元数据。
- 保留设备筛选、实体筛选和电量统计能力。

## 已支持实体

- `climate`：电源、模式、目标温度、当前温度、风模式、扫风模式。
- `switch`：柔风、ECO、电辅热、提示音、灯光、干燥、自学习、蒸发器清洁、光敏等。
- `select`：睡眠模式、上下送风、左右送风等。
- `number`：风速百分比、新风百分比、房间大小等。
- `sensor`：当前/盘管/外机温度、风机转速、电压、电流、压缩机频率、故障码等。

## 安装

将 `custom_components/tcl` 复制到 Home Assistant 配置目录下的
`custom_components` 中，然后重启 Home Assistant。

```text
config/
  custom_components/
    tcl/
      manifest.json
      __init__.py
      ...
```

也可以使用 HACS 自定义仓库安装。

## 配置

1. 打开“设置 -> 设备与服务”。
2. 点击“添加集成”，搜索 `TCL`。
3. 选择 Token、密码或短信验证码登录。
4. 登录后选择需要接入的设备和实体。

## 调试

在 `configuration.yaml` 中加入：

```yaml
logger:
  default: warn
  logs:
    custom_components.tcl: debug
```

## 说明

本项目为非官方集成，TCL 云接口可能随时变化，请自行评估使用风险。
