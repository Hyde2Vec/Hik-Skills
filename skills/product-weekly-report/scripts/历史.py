#!/usr/bin/env python3
"""保存本期材料与主稿，设立默认比较起点。"""
import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

UNSAFE = '\\/:*?"<>|\0'
VERSION_NAME = re.compile(r"^第(\d+)版$")


def fail(message):
    raise ValueError(message)


def dump(data, output=None):
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if output:
        path = Path(output).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    sys.stdout.write(text)


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def require_file(value, kind):
    path = Path(value).expanduser().resolve()
    if path.is_dir():
        fail(f"{kind}必须是文件，不复制目录：{value}")
    if not path.is_file():
        fail(f"找不到{kind}：{value}")
    return path


def require_dir(value, kind):
    path = Path(value).expanduser().resolve()
    if not path.is_dir():
        fail(f"找不到{kind}：{value}")
    return path


def load_json_file(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except UnicodeDecodeError as exc:
        fail(f"{path}不是UTF-8文本：{exc}")
    except json.JSONDecodeError as exc:
        fail(f"{path}不是合法JSON：{exc.msg}（第{exc.lineno}行第{exc.colno}列）")
    if not isinstance(data, (dict, list)):
        fail(f"{path}必须是JSON对象或数组")
    return data


def period_name(value):
    text = str(value).strip()
    if not text:
        fail("周期不能为空")
    for char in UNSAFE:
        text = text.replace(char, "_")
    if text in {".", ".."}:
        fail("周期不合法")
    return text


def report_type(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        fail("报告类型不能为空")
    if text in {".", ".."}:
        fail("报告类型不合法")
    for char in UNSAFE:
        if char in text:
            fail(f"报告类型含非法字符：{value}")
    if VERSION_NAME.fullmatch(text):
        fail(f"报告类型不能与版本目录同名：{text}")
    return text


def recorded_type(record):
    value = record.get("报告类型")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def resolve_type(given, old_record=None):
    if old_record is None:
        return report_type(given)
    old = recorded_type(old_record)
    if given is None:
        return old
    current = report_type(given)
    if current != old:
        fail(f"重做类型不一致：原版本为{old or '未指定'}，本次为{current or '未指定'}")
    return current


def rel(workspace, path):
    try:
        return path.resolve().relative_to(workspace.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def unique_names(paths, kind):
    names = {}
    for path in paths:
        if path.name in names:
            fail(f"{kind}同名，未覆盖：{path.name}")
        names[path.name] = path
    return names


def next_version_dir(workspace, period, kind=None):
    folder = workspace / "周报" / period
    if kind:
        folder = folder / kind
    folder.mkdir(parents=True, exist_ok=True)
    numbers = []
    for child in folder.iterdir():
        match = VERSION_NAME.fullmatch(child.name)
        if match and child.is_dir():
            numbers.append(int(match.group(1)))
    dest = folder / f"第{max(numbers, default=0) + 1}版"
    dest.mkdir(exist_ok=False)
    return dest


def load_version_record(version_dir):
    record_path = version_dir / "工作资料" / "保存记录.json"
    if not record_path.is_file():
        fail(f"原版本目录缺少工作资料/保存记录.json：{version_dir}")
    data = load_json_file(record_path)
    if not isinstance(data, dict):
        fail(f"{record_path} 不是对象")
    return data


def saved_status(material):
    record_path = material.parent / "保存记录.json"
    if not record_path.is_file():
        return None
    data = load_json_file(record_path)
    if not isinstance(data, dict):
        fail(f"{record_path} 不是对象")
    status = data.get("状态")
    if status not in ("草稿", "已确认"):
        fail(f"{record_path} 的状态无法识别：{status}")
    return status


def resolve_redo_basis(args):
    if args.重做 and args.比较依据:
        fail("重做使用 --重做，不能同时指定 --比较依据")
    if not args.重做:
        source = require_file(args.比较依据, "比较依据") if args.比较依据 else None
        return None, source, resolve_type(args.类型)
    redo_dir = require_dir(args.重做, "原版本目录")
    old = load_version_record(redo_dir)
    old_period = str(old.get("周期") or "").strip()
    current_period = str(args.周期).strip()
    if old_period != current_period:
        fail(f"重做周期不一致：原版本为{old_period or '未记录'}，本次为{current_period}")
    kind = resolve_type(args.类型, old)
    old_basis = old.get("比较依据")
    if not old_basis:
        return redo_dir, None, kind
    basis = redo_dir / str(old_basis)
    if not basis.is_file():
        fail(f"原版本缺少冻结的比较依据：{old_basis}")
    return redo_dir, basis, kind


def cmd_save(args):
    workspace = Path(args.工作区).expanduser().resolve()
    period = period_name(args.周期)
    material = require_file(args.材料, "材料")
    draft = require_file(args.主稿, "主稿")
    html = require_file(args.网页, "网页") if args.网页 else None
    products = unique_names([require_file(item, "成品") for item in (args.成品 or [])], "成品")
    extras = unique_names([require_file(item, "附带") for item in (args.附带 or [])], "附带文件")
    redo_dir, basis, kind = resolve_redo_basis(args)
    load_json_file(material)
    draft_name = "周报" + (draft.suffix or ".md")
    html_name = "周报" + (html.suffix or ".html") if html else None
    if html_name and html_name == draft_name:
        fail("主稿与网页目标文件名相同，未覆盖")
    reserved = {"工作资料", draft_name, *( [html_name] if html_name else [] )}
    clash = reserved.intersection(products)
    if clash:
        fail(f"成品同名，未覆盖：{'、'.join(sorted(clash))}")
    workspace.mkdir(parents=True, exist_ok=True)
    dest = next_version_dir(workspace, period, kind)
    data_dir = dest / "工作资料"
    data_dir.mkdir()
    shutil.copy2(draft, dest / draft_name)
    if html:
        shutil.copy2(html, dest / html_name)
    product_names = []
    for name, src in products.items():
        shutil.copy2(src, dest / name)
        product_names.append(name)
    shutil.copy2(material, data_dir / "材料.json")
    basis_rel = None
    if basis is not None:
        basis_name = "比较依据" + (basis.suffix or ".json")
        shutil.copy2(basis, data_dir / basis_name)
        basis_rel = f"工作资料/{basis_name}"
    attached = []
    if extras:
        extra_dir = data_dir / "附带"
        extra_dir.mkdir()
        for name, src in extras.items():
            shutil.copy2(src, extra_dir / name)
            attached.append(f"工作资料/附带/{name}")
    status = "已确认" if args.确认 else "草稿"
    record = {
        "周期": str(args.周期).strip(),
        "报告类型": kind,
        "状态": status,
        "保存时间": datetime.now().isoformat(timespec="seconds"),
        "主稿": draft_name,
        "网页": html_name,
        "成品": product_names,
        "材料": "工作资料/材料.json",
        "比较依据": basis_rel,
        "附带": attached,
        "重做自": rel(workspace, redo_dir) if redo_dir else None,
        "默认起点已移动": False,
    }
    write_json(data_dir / "保存记录.json", record)
    dump({
        "目录": str(dest),
        "周期": record["周期"],
        "报告类型": kind,
        "状态": status,
        "主稿": str(dest / draft_name),
        "网页": str(dest / html_name) if html_name else None,
        "成品": [str(dest / name) for name in product_names],
        "材料": str(data_dir / "材料.json"),
        "比较依据": str(dest / basis_rel) if basis_rel else None,
        "附带": [str(dest / item) for item in attached],
        "重做自": record["重做自"],
        "默认起点已移动": False,
    }, args.输出)


def cmd_baseline(args):
    if not args.确认:
        fail("设置默认起点需要 --确认，表示用户已明确授权")
    workspace = Path(args.工作区).expanduser().resolve()
    material = require_file(args.材料, "材料")
    load_json_file(material)
    status = saved_status(material)
    if status == "草稿":
        fail("未确认草稿不能设为默认起点")
    period = None
    if args.周期 is not None:
        period = str(args.周期).strip()
        period_name(period)
    kind = report_type(args.类型)
    state_dir = workspace / ".周报状态"
    if kind:
        state_dir = state_dir / kind
    state_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    archive = state_dir / "起点历史" / stamp
    archive.mkdir(parents=True, exist_ok=False)
    shutil.copy2(material, archive / "材料.json")
    previous = None
    pointer = state_dir / "默认起点.json"
    if pointer.is_file():
        shutil.copy2(pointer, archive / "原默认起点.json")
        previous = archive / "原默认起点.json"
    now = datetime.now().isoformat(timespec="seconds")
    write_json(archive / "记录.json", {
        "动作": "设起点",
        "周期": period,
        "报告类型": kind,
        "来源": str(material),
        "时间": now,
    })
    payload = {
        "材料": rel(workspace, archive / "材料.json"),
        "周期": period,
        "报告类型": kind,
        "设立时间": now,
    }
    tmp = state_dir / "默认起点.tmp"
    write_json(tmp, payload)
    tmp.replace(pointer)
    dump({
        "默认起点": str(pointer),
        "材料": str(archive / "材料.json"),
        "周期": period,
        "报告类型": kind,
        "原默认起点": str(previous) if previous else None,
    }, args.输出)


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="命令", required=True)
    save = commands.add_parser("保存", help="按周期写入新的第N版；不移动默认起点")
    save.add_argument("--工作区", required=True)
    save.add_argument("--周期", required=True)
    save.add_argument("--材料", required=True)
    save.add_argument("--主稿", required=True)
    save.add_argument("--网页")
    save.add_argument("--成品", nargs="+", default=[], help="PNG/PDF 等成品，复制到版本根部")
    save.add_argument("--比较依据")
    save.add_argument("--重做", help="复制原版本冻结的比较依据（含原来没有依据）")
    save.add_argument("--附带", nargs="+", default=[], help="原表、BI、约定等，放入工作资料/附带")
    save.add_argument("--类型", help="报告类型；省略则沿用单报告路径")
    save.add_argument("--确认", action="store_true")
    save.add_argument("--输出")
    save.set_defaults(func=cmd_save)
    baseline = commands.add_parser("设起点", help="把已确认材料设为默认起点")
    baseline.add_argument("--工作区", required=True)
    baseline.add_argument("--材料", required=True)
    baseline.add_argument("--周期")
    baseline.add_argument("--类型", help="报告类型；省略则沿用单报告路径")
    baseline.add_argument("--确认", action="store_true")
    baseline.add_argument("--输出")
    baseline.set_defaults(func=cmd_baseline)
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except (ValueError, OSError, UnicodeDecodeError) as exc:
        parser.exit(1, f"未完成：{exc}\n")


if __name__ == "__main__":
    main()
