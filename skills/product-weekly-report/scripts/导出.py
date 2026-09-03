#!/usr/bin/env python3
"""导出：把已生成的本地 HTML 渲染成 PNG/PDF。只渲染，不生成、不改写正文。

手机图片优先：默认按 390 CSS px 阅读宽、3 倍像素密度导出整页 PNG，
网页与图片使用同一份 HTML、同一内容与默认可见状态，不做任何扩宽或折叠处理；
PDF 仅用户需要时生成。默认同时运行页面检查（手机 390＋平板 768＋宽屏 1440），一次调用拿到
导出结果与文字化检查 JSON；已人工确认页面、只需导出时加 --仅导出。
导出成功与检查通过分开报告；图表渲染等待失败在任何模式下都按失败返回，
已生成文件保留。"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from 检查页面 import 挂钩, 读取, 等待图表, 能力边界  # noqa: E402

# A4 宽 210mm，左右边距 14mm（与 报告样式.css 的 @page 一致），按 96dpi 换算；
# PDF 打印态检查在此内容宽度下进行。改 @page 边距时必须同步本值。
PDF内容宽 = round((210 - 14 * 2) / 25.4 * 96)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("html", help="已生成的本地 HTML 文件路径")
    parser.add_argument("--png", metavar="路径", help="输出整页 PNG 到该路径（主要产物）")
    parser.add_argument("--pdf", metavar="路径", help="输出 A4 PDF 到该路径（用户需要时）")
    parser.add_argument("--宽度", type=int, default=390,
                        help="阅读视口宽度（默认 390，手机 OA 阅读宽；与网页、图片一致）")
    parser.add_argument("--缩放", type=float, default=3,
                        help="PNG 像素密度 device_scale_factor（默认 3，手机清晰阅读）")
    parser.add_argument("--仅导出", action="store_true", help="跳过页面检查，只导出")
    args = parser.parse_args()
    if not args.png and not args.pdf:
        parser.error("请至少选择一种输出：--png 和/或 --pdf")
    if args.宽度 < 200:
        parser.error("视口宽度过小（不小于 200）")
    return args


def check_target(label, target):
    path = Path(target).expanduser().resolve()
    if path.exists():
        raise ValueError(f"{label} 目标已存在，不覆盖：{path}")
    if not path.parent.is_dir():
        raise ValueError(f"{label} 目标目录不存在：{path.parent}")


def render(html_path, targets, args):
    """手机阅读态检查 → 各格式在最终导出态下检查并导出 → 平板/宽屏响应式检查。

    不展开、不扩宽：报告本身要求全部内容默认可见、适配阅读宽，
    不适配的内容由检查失败暴露，交给 Agent 重排。"""
    from playwright.sync_api import sync_playwright
    results, checks, 等待警告 = [], {}, []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": args.宽度, "height": 800},
                                    device_scale_factor=args.缩放)
            # 图表停动画；导出态标记同时置位：本工具产出的报告不允许折叠必要内容
            page.add_init_script("window.__REPORT_STATIC_EXPORT__ = true;"
                                 "window.__REPORT_EXPANDED_EXPORT__ = true")
            记录 = 挂钩(page)
            page.goto(html_path.as_uri(), wait_until="load")
            page.evaluate("document.fonts.ready.then(() => true)")
            w = 等待图表(page)
            if w:
                等待警告.append("初始加载：" + w)
            for label, target in targets:
                out = Path(target).expanduser().resolve()
                try:
                    if label == "PNG":
                        page.emulate_media(media="screen")
                        if not args.仅导出:
                            checks["手机图片态"] = dict(
                                读取(page, 记录, "手机图片态（阅读宽、停动画）"),
                                视口宽=args.宽度)
                        else:
                            w = 等待图表(page)
                            if w:
                                等待警告.append("PNG 导出前：" + w)
                        高 = page.evaluate(
                            "Math.ceil(document.documentElement.scrollHeight)")
                        page.screenshot(path=str(out), full_page=True)
                        pw, ph = round(args.宽度 * args.缩放), round(高 * args.缩放)
                        results.append((label, f"{out}（布局 {args.宽度}×{高}px，"
                                               f"像素 {pw}×{ph}）", None))
                    else:
                        # PDF 检查与最终 A4 内容宽度一致，
                        # 图表先在最终宽度下重新适配并完成渲染，再检查、再生成
                        page.set_viewport_size({"width": PDF内容宽, "height": 800})
                        page.emulate_media(media="print")
                        page.evaluate("window.dispatchEvent(new Event('resize'))")
                        if not args.仅导出:
                            checks["PDF打印态"] = dict(
                                读取(page, 记录, "PDF 打印态（A4 内容宽、print 媒体）"),
                                视口宽=PDF内容宽)
                        else:
                            w = 等待图表(page)
                            if w:
                                等待警告.append("PDF 导出前：" + w)
                        page.pdf(path=str(out), format="A4", print_background=True)
                        results.append((label, str(out), None))
                except Exception as exc:  # 单个格式失败不牵连其他格式
                    results.append((label, str(out), exc))
            page.close()
            if not args.仅导出:
                # 响应式核对：平板与宽屏两个视口，验证同一内容自适应重排且无越界
                for 标签, 宽 in (("平板", 768), ("宽屏", 1440)):
                    vp = browser.new_page(viewport={"width": 宽, "height": 800})
                    vp记录 = 挂钩(vp)
                    vp.goto(html_path.as_uri(), wait_until="load")
                    checks[标签] = dict(读取(vp, vp记录, f"{标签} {宽}px 响应式态"),
                                      视口宽=宽)
                    vp.close()
        finally:
            browser.close()
    return results, checks, 等待警告


def main():
    args = parse_args()
    html_path = Path(args.html).expanduser().resolve()
    targets = ([("PNG", args.png)] if args.png else []) + \
              ([("PDF", args.pdf)] if args.pdf else [])
    try:
        if not html_path.is_file():
            raise ValueError(f"找不到输入 HTML：{html_path}")
        for label, target in targets:
            check_target(label, target)
        results, checks, 等待警告 = render(html_path, targets, args)
    except (ValueError, ImportError, OSError) as exc:
        sys.exit(f"未完成：{exc}")
    for label, out, exc in results:
        print(f"{label} {'失败：' + str(exc) if exc else '已导出：' + out}")
    失败数 = sum(1 for _, _, exc in results if exc)
    检查通过 = None
    if checks:
        检查通过 = not any(c["存在问题"] for c in checks.values())
        print("检查结果（JSON，与导出结果相互独立）：")
        print(json.dumps({"检查": checks, "检查通过": 检查通过,
                          "图表等待警告": 等待警告, "能力边界": 能力边界},
                         ensure_ascii=False, indent=2))
    else:
        for w in 等待警告:  # --仅导出 时图表未就绪不能静默
            print(f"警告：{w}", file=sys.stderr)
    问题 = []
    if 失败数:
        问题.append(f"{失败数} 项导出失败"
                    + ("；其余格式文件已生成" if 失败数 < len(results) else ""))
    if 检查通过 is False:
        问题.append("检查未通过（导出文件按实际状态保留，问题定位见上方 JSON）")
    if 等待警告:
        问题.append("图表渲染等待未就绪（" + "；".join(等待警告)
                    + "）；已生成文件按实际状态保留，供检查")
    if 问题:
        sys.exit("未完成：" + "；".join(问题))


if __name__ == "__main__":
    main()
