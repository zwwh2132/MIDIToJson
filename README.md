# MIDI 转八音盒乐谱工具

《我的世界》钢琴模组配套工具：将 MIDI 文件转换为游戏内可导入的乐谱 JSON 数据。

## 工具列表

| 文件 | 说明 | 运行方式 |
|------|------|---------|
| `musicbox_converter.html` | 在线网页版（推荐） | 双击浏览器打开，PC/手机通用 |
| `midi_to_musicbox_gui.py` | GUI 桌面版 | `pip install mido` + `py -3 midi_to_musicbox_gui.py` |
| `midi_to_musicbox.py` | 命令行版 | `pip install mido` + `py -3 midi_to_musicbox.py input.mid` |
| `generate_placeholder_textures.py` | 生成占位贴图 | `py -3 generate_placeholder_textures.py` |
| `midi_note_connector.py` | MIDI 音符连接器（命令行版） | `py -3 midi_note_connector.py input.mid output.mid` |
| `midi_note_connector_gui.py` | MIDI 音符连接器（GUI 版） | `py -3 midi_note_connector_gui.py` |

## 使用方式

### 网页版（推荐，无需安装）
双击 `musicbox_converter.html` 在浏览器中打开即可使用。

### 游戏内导入步骤
1. 打开网页工具，上传 MIDI 文件
2. 点击「复制 JSON」复制乐谱数据
3. 进入《我的世界》，手持「空白乐谱」
4. 右键「八音盒」打开界面
5. 点击「导入乐谱」按钮
6. 空白乐谱变为「自定义乐谱」，点击「开始播放」

## 乐谱数据格式

```json
{
    "v": 1,
    "n": "曲名",
    "b": 120,
    "t": [
        [keyIndex, startTick, duration, volume]
    ]
}
```

- `keyIndex`: 0-20，对应钢琴的 C4~B6 白键
- `startTick`: 起始 tick（1 tick = 1/4 拍）
- `duration`: 持续 tick 数
- `volume`: 音量 0.3-1.0
