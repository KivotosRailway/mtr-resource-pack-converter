"""Loss-aware conversion of the common built-in-vehicle retexture subset.

The MTR 3 train type and MTR 4 vehicle family have different semantics. Custom
models, per-car textures, scripts and parts require a human-authored mapping.
"""

from __future__ import annotations

import copy
import json
import re
import zipfile
from pathlib import Path, PurePosixPath


RESOURCE = "assets/mtr/mtr_custom_resources.json"
MAX_FILE = 128 * 1024 * 1024
MAX_TOTAL = 1024 * 1024 * 1024
ID = re.compile(r"^[a-z0-9_.-]+$")


class ConvertError(ValueError):
    pass


def _json(data: bytes, name: str) -> dict:
    try:
        obj = json.loads(data.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ConvertError(f"{name}: JSON 无法解析：{exc}") from exc
    if not isinstance(obj, dict):
        raise ConvertError(f"{name}: 顶层必须是 JSON 对象")
    return obj


def _bytes_json(obj: dict) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _safe_name(name: str) -> str:
    if "\\" in name or "\0" in name:
        raise ConvertError(f"不安全的文件名：{name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or not name or any(part in (".", "..") for part in name.split("/")):
        raise ConvertError(f"不安全的文件名：{name!r}")
    return name


def read_pack(path: str | Path) -> dict[str, bytes]:
    path = Path(path)
    if not path.exists():
        raise ConvertError(f"输入不存在：{path}")
    files: dict[str, bytes] = {}
    total = 0
    if path.is_dir():
        for file in path.rglob("*"):
            if file.is_symlink():
                raise ConvertError(f"不接受符号链接：{file}")
            if not file.is_file():
                continue
            name = _safe_name(file.relative_to(path).as_posix())
            size = file.stat().st_size
            total += size
            if size > MAX_FILE or total > MAX_TOTAL:
                raise ConvertError("输入超过大小限制")
            files[name] = file.read_bytes()
    elif path.is_file() and zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                name = _safe_name(info.filename.rstrip("/"))
                if info.is_dir():
                    continue
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ConvertError(f"不接受 ZIP 符号链接：{name}")
                total += info.file_size
                if info.file_size > MAX_FILE or total > MAX_TOTAL:
                    raise ConvertError("输入超过大小限制")
                if name in files:
                    raise ConvertError(f"ZIP 中存在重复文件：{name}")
                data = archive.read(info)
                if len(data) != info.file_size:
                    raise ConvertError(f"文件长度异常：{name}")
                files[name] = data
    else:
        raise ConvertError("输入必须是资源包 ZIP 或目录")
    if RESOURCE not in files:
        raise ConvertError(f"未找到 {RESOURCE}，请确认 ZIP 根目录正确")
    return files


def _format(obj: dict) -> str:
    old = isinstance(obj.get("custom_trains"), dict)
    new = isinstance(obj.get("vehicles"), list)
    if old and new:
        raise ConvertError("同时存在 custom_trains 和 vehicles，无法自动判断格式")
    if old:
        return "3.2"
    if new:
        return "4.0"
    raise ConvertError("未识别到 MTR 3.2 custom_trains 或 MTR 4.0 vehicles")


def inspect_pack(path: str | Path) -> dict:
    files = read_pack(path)
    config = _json(files[RESOURCE], RESOURCE)
    fmt = _format(config)
    key = "custom_trains" if fmt == "3.2" else "vehicles"
    return {"format": fmt, "vehicles_or_trains": len(config[key]),
            "files": len(files), "sections": sorted(config.keys())}


def _check_sections(obj: dict, allowed: set[str], issues: list[str]) -> None:
    for key, value in obj.items():
        if key not in allowed and value not in (None, {}, []):
            issues.append(f"顶层字段 {key} 无自动转换规则")


def _family(vehicle: dict) -> str | None:
    tags = vehicle.get("tags", [])
    if not isinstance(tags, list):
        return None
    return next((tag[7:] for tag in tags if isinstance(tag, str) and tag.startswith("family:")), None)


def _load_template(path: str | Path) -> list[dict]:
    path = Path(path)
    if path.suffix.lower() == ".json":
        obj = _json(path.read_bytes(), str(path))
    else:
        obj = _json(read_pack(path)[RESOURCE], str(path))
    if not isinstance(obj.get("vehicles"), list):
        raise ConvertError("模板必须含有 MTR 4 vehicles 数组")
    return obj["vehicles"]


def _retexture_model(model: dict, texture: str) -> bool:
    # Door overlays and special bogies keep their own UV and texture.
    mr = model.get("modelResource", "")
    tr = model.get("textureResource", "")
    if not isinstance(mr, str) or not isinstance(tr, str):
        return False
    if (mr.startswith("mtr:models/vehicle/") and "overlay" not in mr
            and tr.startswith("mtr:textures/vehicle/") and "bogie" not in mr):
        model["textureResource"] = texture
        return True
    return False


def _to_four(source: dict, template: list[dict], issues: list[str]) -> tuple[dict, int]:
    _check_sections(source, {"custom_trains"}, issues)
    output: dict = {"vehicles": [], "signs": [], "rails": [], "objects": [], "lifts": []}
    used_ids: set[str] = set()
    count = 0
    for train_id, train in source["custom_trains"].items():
        if not isinstance(train, dict) or not ID.fullmatch(train_id):
            issues.append(f"列车 ID {train_id!r} 无效")
            continue
        base = train.get("base_train_type")
        texture = train.get("texture_id")
        if train.get("model") or train.get("model_properties") or train.get("script_files"):
            issues.append(f"{train_id}: 自定义模型或脚本需要人工重建车厢结构")
            continue
        if not isinstance(base, str) or not isinstance(texture, str):
            issues.append(f"{train_id}: 只支持包含 base_train_type 和 texture_id 的换皮车")
            continue
        matches = [v for v in template if isinstance(v, dict) and _family(v) == base]
        if not matches:
            issues.append(f"{train_id}: 模板中没有 family:{base} 的车辆")
            continue
        staged = []
        for base_vehicle in matches:
            variant = copy.deepcopy(base_vehicle)
            base_id = variant.get("id")
            if not isinstance(base_id, str):
                issues.append(f"{train_id}: 模板车辆缺少 id")
                break
            variant["id"] = f"{train_id}_{base_id}"
            if variant["id"] in used_ids:
                issues.append(f"{train_id}: 输出车辆 ID 冲突：{variant['id']}")
                break
            variant["name"] = f"{train.get('name', train_id)} · {base_vehicle.get('name', base_id)}"
            for old, new in (("color", "color"), ("description", "description"),
                             ("wikipedia_article", "wikipediaArticle"),
                             ("speed_sound_base_id", "legacySpeedSoundBaseResource"),
                             ("speed_sound_count", "legacySpeedSoundCount"),
                             ("door_sound_base_id", "legacyDoorSoundBaseResource"),
                             ("door_close_sound_time", "legacyDoorCloseSoundTime"),
                             ("bve_sound_base_id", "bveSoundBaseResource")):
                if old in train:
                    variant[new] = train[old]
            tags = variant.get("tags", [])
            variant["tags"] = [f"family:{train_id}" if tag == f"family:{base}" else tag for tag in tags]
            replaced = sum(_retexture_model(m, texture) for m in variant.get("models", []) if isinstance(m, dict))
            if not replaced:
                issues.append(f"{train_id}: 模板车辆 {base_id} 没有可替换的原版车体贴图")
                break
            staged.append(variant)
        else:
            output["vehicles"].extend(staged)
            used_ids.update(v["id"] for v in staged)
            count += 1
            known = {"name", "base_train_type", "texture_id", "color", "description",
                     "wikipedia_article", "speed_sound_base_id", "speed_sound_count",
                     "door_sound_base_id", "door_close_sound_time", "bve_sound_base_id"}
            for key in train.keys() - known:
                issues.append(f"{train_id}: 字段 {key} 未转换")
    return output, count


def _to_three(source: dict, base_map: dict[str, str], issues: list[str]) -> tuple[dict, int]:
    _check_sections(source, {"vehicles", "signs", "rails", "objects", "lifts"}, issues)
    for section in ("signs", "rails", "objects", "lifts"):
        if source.get(section):
            issues.append(f"{section}: MTR 4 专用定义无法自动转换")
    families: dict[str, list[dict]] = {}
    for vehicle in source["vehicles"]:
        if not isinstance(vehicle, dict):
            issues.append("vehicles 包含非对象条目")
            continue
        family = _family(vehicle)
        if not family or not ID.fullmatch(family):
            issues.append(f"车辆 {vehicle.get('id', '?')}: 缺少合法 family:xxx 标签")
            continue
        families.setdefault(family, []).append(vehicle)
    trains: dict[str, dict] = {}
    for family, vehicles in families.items():
        textures: set[str] = set()
        valid = True
        for vehicle in vehicles:
            if vehicle.get("transportMode", "TRAIN") != "TRAIN":
                valid = False
            models = vehicle.get("models", [])
            if not isinstance(models, list) or not models:
                valid = False
                continue
            for model in models:
                if not isinstance(model, dict):
                    valid = False
                    continue
                mr = model.get("modelResource", "")
                tr = model.get("textureResource", "")
                if not isinstance(mr, str) or not mr.startswith("mtr:models/vehicle/"):
                    valid = False
                if "overlay" not in mr and isinstance(tr, str) and not tr.startswith("mtr:textures/overlay/"):
                    textures.add(tr)
        custom = {t for t in textures if not t.startswith("mtr:textures/vehicle/")}
        if not valid or len(custom) != 1 or len(textures - custom) > 1:
            issues.append(f"{family}: 只能降级使用原版车体模型及一张统一自定义车体贴图的车辆族")
            continue
        base = base_map.get(family, family)
        if not ID.fullmatch(base):
            issues.append(f"{family}: 旧版基础车型 ID {base!r} 无效")
            continue
        first = vehicles[0]
        train: dict = {"name": first.get("name", family), "base_train_type": base,
                       "texture_id": next(iter(custom))}
        for old, new in (("color", "color"), ("description", "description"),
                         ("wikipediaArticle", "wikipedia_article"),
                         ("legacySpeedSoundBaseResource", "speed_sound_base_id"),
                         ("legacySpeedSoundCount", "speed_sound_count"),
                         ("legacyDoorSoundBaseResource", "door_sound_base_id"),
                         ("legacyDoorCloseSoundTime", "door_close_sound_time"),
                         ("bveSoundBaseResource", "bve_sound_base_id")):
            if old in first:
                train[new] = first[old]
        trains[family] = train
        issues.append(f"{family}: 车厢编组、部件动画、贯通道等 4.0 属性不能映射到 3.2")
    return {"custom_trains": trains}, len(trains)


def convert(input_path: str | Path, output_path: str | Path, *, target: str,
            template: str | Path | None = None, base_map: dict[str, str] | None = None,
            allow_partial: bool = False, pack_format: int | None = None) -> dict:
    files = read_pack(input_path)
    source = _json(files[RESOURCE], RESOURCE)
    origin = _format(source)
    if target not in ("3.2", "4.0") or target == origin:
        raise ConvertError(f"源格式是 {origin}，目标必须是另一种格式")
    issues: list[str] = []
    if target == "4.0":
        if template is None:
            raise ConvertError("3.2→4.0 换皮车辆需要 --template 指向 MTR 4 官方车辆定义 JSON/ZIP")
        result, converted = _to_four(source, _load_template(template), issues)
    else:
        result, converted = _to_three(source, base_map or {}, issues)
    report = {"source": origin, "target": target, "converted_groups": converted,
              "issues": issues, "partial": bool(issues)}
    if not converted:
        raise ConvertError("没有可转换的车辆；" + "；".join(issues[:5]))
    if issues and not allow_partial:
        raise ConvertError("检测到可能丢失的内容，未写入输出。添加 --allow-partial 可继续。\n" + "\n".join(issues))
    files[RESOURCE] = _bytes_json(result)
    if pack_format is not None:
        if pack_format <= 0:
            raise ConvertError("pack_format 必须是正整数")
        meta = _json(files.get("pack.mcmeta", b'{"pack":{}}'), "pack.mcmeta")
        meta.setdefault("pack", {})["pack_format"] = pack_format
        files["pack.mcmeta"] = _bytes_json(meta)
    if issues:
        files["mtr_converter/original_mtr_custom_resources.json"] = _bytes_json(source)
    output = Path(output_path)
    if output.exists() or output.resolve() == Path(input_path).resolve():
        raise ConvertError(f"输出已存在或与输入相同：{output}")
    if output.suffix.lower() != ".zip":
        raise ConvertError("输出路径必须以 .zip 结尾")
    output.parent.mkdir(parents=True, exist_ok=True)
    # ZIP is written to a sibling temporary file to avoid incomplete deliverables.
    temp = output.with_name(output.name + ".tmp")
    try:
        with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for name in sorted(files):
                archive.writestr(name, files[name])
        temp.replace(output)
        report_path = output.with_name(output.stem + ".report.json")
        report_path.write_bytes(_bytes_json(report))
    finally:
        temp.unlink(missing_ok=True)
    return report
