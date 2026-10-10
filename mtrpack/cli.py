"""Command-line interface. Standard library only."""

import argparse
import json
import sys

from .converter import ConvertError, convert, inspect_pack


def main(argv=None):
    parser = argparse.ArgumentParser(description="MTR 3.2 / 4.0 资源包转换器")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("inspect", help="检测格式和主要条目")
    check.add_argument("input")
    run = sub.add_parser("convert", help="转换 ZIP 或文件夹并生成 ZIP")
    run.add_argument("input")
    run.add_argument("output")
    run.add_argument("--to", required=True, choices=("3.2", "4.0"))
    run.add_argument("--template", help="MTR 4 原版车辆定义 JSON 或资源包 ZIP，用于 3.2→4.0")
    run.add_argument("--base-map", help="可选 JSON，4.0 family 到 3.2 base_train_type 的映射")
    run.add_argument("--allow-partial", action="store_true", help="保留原定义备份，接受报告中的转换缺口")
    run.add_argument("--pack-format", type=int, help="按目标 Minecraft 版本设定 pack.mcmeta 数字")
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            result = inspect_pack(args.input)
        else:
            base_map = None
            if args.base_map:
                with open(args.base_map, encoding="utf-8") as file:
                    base_map = json.load(file)
                if not isinstance(base_map, dict) or not all(isinstance(k, str) and isinstance(v, str)
                                                             for k, v in base_map.items()):
                    raise ConvertError("--base-map 必须是字符串到字符串的 JSON 对象")
            result = convert(args.input, args.output, target=args.to, template=args.template,
                             base_map=base_map, allow_partial=args.allow_partial,
                             pack_format=args.pack_format)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ConvertError, OSError, json.JSONDecodeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
