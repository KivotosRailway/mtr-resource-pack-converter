# MTR 3.2 ↔ MTR 4.0 资源包转换器

这是一个使用 Python 标准库的离线项目。它针对**原版车型换皮资源包**提供双向转换，并对不能安全转换的内容出具报告。输入可以是 ZIP 或目录；输出为新的 ZIP，不覆盖原包。当前专注于 `assets/mtr/mtr_custom_resources.json` 中的列车/车辆定义，图片、模型、声音等文件按原字节保留。

项目代码采用仓库根目录的 BSD 3-Clause 许可证；转换后的资源包仍受原资源包作者的授权约束。

## 运行环境

Python 3.10 或更新版本。进入本项目目录，在终端运行：

```bash
python -m mtrpack inspect 原资源包.zip
```

Windows/macOS/Linux 若安装了 Tkinter，也可以运行 `python launch_gui.py` 打开文件选择界面。命令行还支持输入文件夹；GUI 当前选择 ZIP 文件。

### 3.2 → 4.0

需要 MTR 4 官方的车辆定义作为模板，因为一个 MTR 3 列车类型对应 MTR 4 的多个车厢（驾驶室、拖车等），不能仅靠改 JSON 字段得到正确编组。在 MTR 4 模组中找到包含 `vehicles` 数组的 `mtr_custom_resources.json`，保存为 `mtr4_template.json`；也可传入包含该文件的 ZIP。模板须包含旧版 `base_train_type` 对应的 `family:车型ID` 车辆族。

```bash
python -m mtrpack convert old.zip new-4.zip --to 4.0 --template mtr4_template.json
```

转换器复制该车型族的车辆定义，替换原版车体贴图，保留门贴图，并替换 ID、名称、颜色和常见声音字段。旧包的模型、贴图、声音仍保存在输出 ZIP。只支持不含自定义模型或脚本的 `custom_trains` 换皮列车。

### 4.0 → 3.2

MTR 4 的车辆必须有相同的 `family:xxx` 标签、使用原版 `mtr:models/vehicle/` 模型，并统一使用一张自定义车体贴图。旧版基础车型 ID 如与族名不同，可提供映射：

```json
{"blue_train": "sp1900"}
```

```bash
python -m mtrpack convert new-4.zip old-3.zip --to 3.2 --base-map mapping.json --allow-partial
```

4.0 的独立车厢、部件动画和编组属性在 3.2 没有直接等价定义，因此反向转换始终会提示这一差异，并要求显式使用 `--allow-partial`。**建议先在 MTR 3.2 中检查车型与车门。** 如果 4.0 原包还包含标牌、轨道、装饰物等专用定义，会一并列入报告。

## 报告与保护

- 成功后生成 `输出文件.report.json`，记录转换数量和每项缺口。
- 默认遇到可能丢失的内容时拒绝写入输出；`--allow-partial` 会把原始定义另存于 ZIP 内的 `mtr_converter/original_mtr_custom_resources.json`，便于手动补充。
- 原 ZIP 不会被修改；输出文件如果已存在会拒绝覆盖。
- `pack.mcmeta` 中的 `pack_format` 对应 **Minecraft 版本**，不是 MTR 版本。默认保留；如需调整，请按目标 Minecraft 版本使用 `--pack-format 数字`。
- ZIP 路径、重复文件、符号链接以及解压后大小均会检查。

## 目前的边界

这个工具尚不能自动转换自定义 BBMODEL/OBJ 的模型属性、NTE 脚本、动态显示屏、车门动画，或将 MTR 4 独立车厢精确还原成 MTR 3 的可变长度列车。这些需要原包实例及游戏内测试来建立规则。MTR 4 官方资源包创建器本身也支持导入 MTR 3 包并尝试导出 MTR 4 包；复杂的 3→4 包可以用它作交叉检查。

## 开发测试

```bash
python -m unittest discover -s tests -v
```

参考资料：

- [MTR 官方 Wiki：4.0 自定义资源迁移](https://wiki.minecrafttransitrailway.com/mtr:4.0.x:content_developer)
- [MTR 官方 Wiki：资源包创建器](https://wiki.minecrafttransitrailway.com/resourcepack:make:rp_creator)
- [MTR 官方 Wiki：4.0 原版车辆定义示例](https://wiki.minecrafttransitrailway.com/mtr_extra:resourcepack:make:core_mod_custom_resources)
