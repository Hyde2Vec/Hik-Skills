#!/usr/bin/env python3
"""检查页面：真正打开本地 HTML，输出文字化 JSON 检查结果（默认 390/768/1440 三视口）。

供不依赖截图的流程使用：页面错误、资源/图片加载失败、文档水平溢出、
元素越界、固定高度/hidden 文字裁切、td.num 数值拆行、未展开折叠、表格横向溢出。
能力边界印在每次输出的“能力边界”字段中。导出.py 复用本模块的 挂钩/读取/等待图表。"""
import argparse
import json
import sys
from pathlib import Path

能力边界 = (
    "本检查覆盖：页面脚本错误、资源与图片加载失败、文档水平溢出、元素越界、"
    "固定高度/hidden 造成的文字裁切、td.num 数值单元格拆行（Range 几何）、"
    "未展开的折叠明细（报告不允许藏明细，一律计为问题）、"
    "表格横向溢出（各视口下整表须可见，溢出即需重排）、"
    "图表实例数量/容器尺寸/是否有实际渲染内容/图表内 SVG 文本包围盒重叠"
    "（默认手机 390、平板 768、宽屏 1440 三个视口）。"
    "打印态检查为与 A4 内容宽度一致的近似几何，不逐页核对 PDF 分页效果。"
    "不覆盖：美观与配色判断、语义与事实正确性；DOM 几何检查不等于完整视觉验收，"
    "重要交付仍可由用户或有视觉能力的模型复核截图。"
)

# 在页面内执行的几何与状态检查；宽表格容器（.table-wrap）内部允许横向滚动，不算越界/裁切。
检查脚本 = r"""
() => {
  const 页面宽 = document.documentElement.clientWidth;
  const 路径 = el => {
    const 段 = [];
    for (let cur = el; cur && cur !== document.body && 段.length < 3; cur = cur.parentElement) {
      let s = cur.tagName.toLowerCase();
      if (cur.classList.length) s += '.' + [...cur.classList].slice(0, 2).join('.');
      段.unshift(s);
    }
    return 段.join(' > ');
  };
  const 摘要 = el => (el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 40);
  const 越界 = [], 裁切 = [];
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    const wrap = el.closest('.table-wrap');
    if (wrap && el !== wrap) continue;  // 宽表内容在容器内滚动，容器本身仍受检
    if ((r.right > 页面宽 + 1 || r.left < -1) && 越界.length < 10)
      越界.push({元素: 路径(el), 文字: 摘要(el), 左: Math.round(r.left), 右: Math.round(r.right)});
  }
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    const cs = getComputedStyle(el);
    if (['hidden', 'clip'].includes(cs.overflowY) && el.scrollHeight > el.clientHeight + 2
        && 裁切.length < 10)
      裁切.push({元素: 路径(el), 文字: 摘要(el), 方向: '纵向', 可见高: el.clientHeight, 实际高: el.scrollHeight});
    if (['hidden', 'clip'].includes(cs.overflowX) && el.scrollWidth > el.clientWidth + 2
        && !el.classList.contains('table-wrap') && 裁切.length < 10)
      裁切.push({元素: 路径(el), 文字: 摘要(el), 方向: '横向', 可见宽: el.clientWidth, 实际宽: el.scrollWidth});
  }
  // td.num 数值拆行检测：Range 几何看同一非空值是否被拆成多行；
  // 只查数据单元格（表头允许换行），折叠内零尺寸自然略过，宽表容器内同样检查
  const 拆行 = [];
  for (const el of document.querySelectorAll('td.num')) {
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    if (!(el.textContent || '').trim()) continue;
    const range = document.createRange();
    range.selectNodeContents(el);
    const 行 = new Set([...range.getClientRects()]
      .filter(x => x.width > 0).map(x => Math.round(x.top)));
    if (行.size > 1 && 拆行.length < 10)
      拆行.push({元素: 路径(el), 文字: 摘要(el), 行数: 行.size});
  }
  return {
    文档水平溢出: document.documentElement.scrollWidth > 页面宽 + 1,
    越界元素: 越界,
    文字裁切: 裁切,
    数值拆行: 拆行,
    图片失败: [...document.images].filter(i => !(i.complete && i.naturalWidth > 0))
      .map(i => i.currentSrc || i.src || '(无 src)'),
    折叠明细: {总数: document.querySelectorAll('details').length,
               未展开: document.querySelectorAll('details:not([open])').length},
    // 表格横向溢出：手机阅读宽下表格必须整表可见，溢出即需重排（少列表/键值行/逐条明细）
    表格溢出: [...document.querySelectorAll('.table-wrap')]
      .map((w, i) => ({序号: i + 1, 列数: (w.querySelector('table tr') || {cells: []}).cells.length,
                       内容宽: w.scrollWidth, 可见宽: w.clientWidth}))
      .filter(x => x.内容宽 > x.可见宽 + 1),
    字体状态: document.fonts.status,
    // 图表可验证信息：实例数量、容器尺寸、是否有实际渲染内容；不做美观判断
    图表: (() => {
      const 容器 = [...document.querySelectorAll('.chart')];
      if (!window.echarts && !容器.length) return null;
      // 导出态由导出工具在加载时置位：导出的报告不允许折叠必要内容，图表必须全部可见且已渲染；
      // 独立运行本脚本检查时不置位，折叠内零尺寸图表按不可见略过
      const 导出态 = !!window.__REPORT_EXPANDED_EXPORT__;
      if (!window.echarts)
        return {库加载: false, 导出态, 容器数: 容器.length, 数量: 0, 实例: [],
                未初始化容器: 容器.map(路径)};
      const 实例 = (window.__报告图表 || []).map(c => {
        const el = c.getDom(), r = el.getBoundingClientRect();
        const svg = el.querySelector('svg');
        return {容器: 路径(el), 宽: Math.round(r.width), 高: Math.round(r.height),
                可见: r.width > 0 && r.height > 0,
                已释放: c.isDisposed(), 有渲染内容: !!(svg && svg.childElementCount)};
      });
      const 未初始化容器 = 容器.filter(el => !echarts.getInstanceByDom(el)).map(路径);
      // SVG 文本重叠诊断：仅比较图表内可见 text 的包围盒（如图例与纵轴单位）。
      // 注意：比较的是轴对齐包围盒而非字形轮廓，旋转标签等情形可能误报边缘接触；
      // 本检查只用于发现真实可复现的文本互叠，不推广为通用碰撞检测。
      const 文本重叠 = [];
      for (const c of (window.__报告图表 || [])) {
        const el = c.getDom();
        const r0 = el.getBoundingClientRect();
        if (!r0.width || !r0.height) continue;  // 不可见容器跳过
        const ts = [...el.querySelectorAll('text')]
          .map(t => ({t, r: t.getBoundingClientRect()}))
          .filter(x => x.r.width > 0 && x.r.height > 0);
        for (let i = 0; i < ts.length && 文本重叠.length < 8; i++)
          for (let j = i + 1; j < ts.length && 文本重叠.length < 8; j++) {
            const a = ts[i].r, b = ts[j].r;
            const x = Math.max(a.left, b.left), y = Math.max(a.top, b.top);
            const w = Math.min(a.right, b.right) - x, h = Math.min(a.bottom, b.bottom) - y;
            if (w > 1 && h > 1)
              文本重叠.push({容器: 路径(el),
                文字: [(ts[i].t.textContent || '').trim().slice(0, 20),
                       (ts[j].t.textContent || '').trim().slice(0, 20)],
                交集: {x: Math.round(x), y: Math.round(y), 宽: Math.round(w), 高: Math.round(h)}});
          }
      }
      return {库加载: true, 导出态, 容器数: 容器.length, 数量: 实例.length, 实例,
              未初始化容器, 文本重叠};
    })(),
  };
}
"""


def 图表问题(图表):
    """可见但未渲染、已释放、容器未初始化、SVG 文本重叠都算问题；
    完整导出态下不可见/未渲染也算。"""
    if not 图表:
        return False
    if not 图表["库加载"] or 图表["未初始化容器"]:
        return True
    if 图表.get("文本重叠"):
        return True
    return any(
        i["已释放"]
        or (i["可见"] and not i["有渲染内容"])
        or (图表["导出态"] and (not i["可见"] or not i["有渲染内容"]))
        for i in 图表["实例"])


def 等待图表(page):
    """无 echarts 或渲染就绪返回 None；超时/失败返回错误描述，绝不吞掉。"""
    if not page.evaluate("!!window.echarts"):
        return None
    try:
        page.wait_for_function("(window.__图表待完成 || 0) === 0", timeout=8000)
        return None
    except Exception as exc:
        return f"图表渲染等待未就绪：{exc}"


def 挂钩(page):
    """在 goto 前挂上错误与资源监听，返回记录字典。"""
    记录 = {"页面错误": [], "资源加载失败": []}
    page.on("pageerror", lambda e: 记录["页面错误"].append(str(e)[:200]))
    page.on("requestfailed", lambda r: 记录["资源加载失败"].append(
        f"{r.url[:120]}（{r.failure or '未知原因'}）"))
    return 记录


def 读取(page, 记录, 阶段=""):
    """等待字体与图表就绪后执行页面检查，合并记录，并给出该视口是否存在问题。"""
    page.evaluate("document.fonts.ready.then(() => true)")
    等待失败 = 等待图表(page)
    数据 = page.evaluate(检查脚本)
    数据.update(记录)
    if 阶段:
        数据["阶段"] = 阶段
    数据["图表等待"] = 等待失败 or "就绪"
    数据["存在问题"] = bool(记录["页面错误"] or 记录["资源加载失败"] or 数据["图片失败"]
                       or 数据["文档水平溢出"] or 数据["越界元素"] or 数据["文字裁切"]
                       or 数据["数值拆行"] or 数据["表格溢出"]
                       or 数据["折叠明细"]["未展开"]
                       or 图表问题(数据.get("图表")) or 等待失败)
    return 数据


def 检查(html_path, widths):
    from playwright.sync_api import sync_playwright
    if not html_path.is_file():
        raise ValueError(f"找不到输入 HTML：{html_path}")
    结果 = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for width in widths:
                page = browser.new_page(viewport={"width": width, "height": 800})
                记录 = 挂钩(page)
                page.goto(html_path.as_uri(), wait_until="load")
                数据 = 读取(page, 记录)
                数据["视口宽"] = width
                结果.append(数据)
                page.close()
        finally:
            browser.close()
    return 结果


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("html", help="已生成的本地 HTML 文件路径")
    parser.add_argument("--手机宽度", type=int, default=390, help="手机阅读视口宽度（默认 390）")
    parser.add_argument("--仅手机", action="store_true", help="只检查手机阅读宽度，跳过 768/1440")
    args = parser.parse_args()
    widths = [args.手机宽度] + ([] if args.仅手机 else [768, 1440])
    if any(w < 200 for w in widths):
        parser.error("视口宽度过小（不小于 200）")
    try:
        结果 = 检查(Path(args.html).expanduser().resolve(), widths)
    except (ValueError, ImportError, OSError) as exc:
        sys.exit(f"未完成：{exc}")
    通过 = not any(r["存在问题"] for r in 结果)
    print(json.dumps({"文件": str(Path(args.html).expanduser().resolve()),
                      "检查": 结果, "通过": 通过, "能力边界": 能力边界},
                     ensure_ascii=False, indent=2))
    sys.exit(0 if 通过 else 1)


if __name__ == "__main__":
    main()
