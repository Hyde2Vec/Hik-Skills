/* 图表.js — 报告图表通用主题与初始化助手
   用法：先加载 vendor/echarts.min.js，再加载本文件，然后
     初始化图表(容器元素, option)   // 返回 echarts 实例
   SVG 渲染；配色、字体与 报告样式.css 一致；导出工具注入 __REPORT_STATIC_EXPORT__ 时自动停动画。
   图表只负责呈现给定数据：统计计算、因果与业务结论由正文和数据负责，不在这里做。 */
(function () {
  "use strict";

  var 基础 = {
    animation: !window.__REPORT_STATIC_EXPORT__,
    color: ["#1e2a38", "#8a6a45", "#5b7062", "#77603c", "#9aa0a6"],
    textStyle: {
      fontFamily: '-apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Source Han Sans SC", sans-serif',
      fontSize: 12,
      color: "#33383f"
    },
    grid: { left: 8, right: 16, top: 40, bottom: 8, containLabel: true },
    // 图例固定顶部右对齐：纵轴名称/单位默认在左上，两者分区互不重叠；grid 顶部留白 40px
    legend: { top: 0, right: 0, textStyle: { color: "#6f757c", fontSize: 12 }, itemWidth: 14, itemHeight: 8 },
    tooltip: {
      backgroundColor: "#ffffff",
      borderColor: "#d3cfc3",
      textStyle: { color: "#33383f", fontSize: 12 },
      extraCssText: "box-shadow:0 2px 8px rgba(30,42,56,.12);"
    },
    xAxis: {
      axisLine: { lineStyle: { color: "#d3cfc3" } },
      axisTick: { show: false },
      axisLabel: { color: "#6f757c" }
    },
    yAxis: {
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: "#e4e1d9" } },
      axisLabel: { color: "#6f757c" }
    }
  };

  window.__报告图表 = [];
  window.__图表待完成 = 0;

  function 适配() {
    window.__报告图表.forEach(function (c) {
      if (!c.isDisposed()) c.resize();
    });
  }

  window.初始化图表 = function (el, option) {
    if (!window.echarts) throw new Error("未加载 echarts：先引入 vendor/echarts.min.js");
    var chart = echarts.init(el, null, { renderer: "svg" });
    window.__图表待完成++;
    chart.on("finished", function () {
      window.__图表待完成 = Math.max(0, window.__图表待完成 - 1);
    });
    chart.setOption(基础);      // 主题默认值
    chart.setOption(option);   // 本次数据与配置（echarts 合并语义）
    window.__报告图表.push(chart);
    return chart;
  };

  window.addEventListener("resize", 适配);
  // 打印前后重新适配，避免容器尺寸变化后图形变形
  window.addEventListener("beforeprint", 适配);
  window.addEventListener("afterprint", 适配);
})();
