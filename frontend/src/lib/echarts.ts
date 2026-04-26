import * as echarts from 'echarts/core'
import {
  LineChart,
  BarChart,
  PieChart,
  SunburstChart,
  TreemapChart,
  HeatmapChart,
  CustomChart,
} from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DatasetComponent,
  TitleComponent,
  MarkLineComponent,
  MarkAreaComponent,
  MarkPointComponent,
  ToolboxComponent,
  DataZoomComponent,
  VisualMapComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useEffect, useState } from 'react'
import type { EChartsOption } from 'echarts'

// Register only what we use — keeps the bundle around 90-110 kB gz instead of 350+.
echarts.use([
  LineChart,
  BarChart,
  PieChart,
  SunburstChart,
  TreemapChart,
  HeatmapChart,
  CustomChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DatasetComponent,
  TitleComponent,
  MarkLineComponent,
  MarkAreaComponent,
  MarkPointComponent,
  ToolboxComponent,
  DataZoomComponent,
  VisualMapComponent,
  CanvasRenderer,
])

export type ChartTokens = {
  bgBase: string
  bgElev: string
  borderBase: string
  textPrimary: string
  textSecondary: string
  textTertiary: string
  gain: string
  loss: string
  flat: string
  accent: string
  chartGrid: string
  chartAxis: string
  chartTooltipBg: string
  chartTooltipBorder: string
  categorical: string[]
}

function readVar(name: string): string {
  if (typeof document === 'undefined') return ''
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

export function readChartTokens(): ChartTokens {
  return {
    bgBase: readVar('--bg-base'),
    bgElev: readVar('--bg-elev'),
    borderBase: readVar('--border-base'),
    textPrimary: readVar('--text-primary'),
    textSecondary: readVar('--text-secondary'),
    textTertiary: readVar('--text-tertiary'),
    gain: readVar('--gain'),
    loss: readVar('--loss'),
    flat: readVar('--flat'),
    accent: readVar('--accent'),
    chartGrid: readVar('--chart-grid'),
    chartAxis: readVar('--chart-axis'),
    chartTooltipBg: readVar('--chart-tooltip-bg'),
    chartTooltipBorder: readVar('--chart-tooltip-border'),
    categorical: [
      readVar('--cat-1'),
      readVar('--cat-2'),
      readVar('--cat-3'),
      readVar('--cat-4'),
      readVar('--cat-5'),
      readVar('--cat-6'),
      readVar('--cat-7'),
      readVar('--cat-8'),
    ],
  }
}

/**
 * Build an ECharts theme object from current CSS variables. Re-derive whenever
 * the active theme changes; pass the result via the `theme=` prop of the
 * chart wrapper, or as `<EChartsReact theme={'pt'} ...>` after registering.
 */
export function buildEChartsTheme(t: ChartTokens) {
  return {
    color: t.categorical,
    backgroundColor: 'transparent',
    textStyle: { color: t.textPrimary, fontFamily: 'inherit' },
    title:    { textStyle: { color: t.textPrimary } },
    legend:   { textStyle: { color: t.textSecondary } },
    tooltip: {
      backgroundColor: t.chartTooltipBg,
      borderColor: t.chartTooltipBorder,
      borderWidth: 1,
      textStyle: { color: t.textPrimary, fontFamily: 'inherit' },
      extraCssText: 'box-shadow: 0 4px 12px rgba(0,0,0,0.25); border-radius: 6px;',
    },
    categoryAxis: {
      axisLine:  { lineStyle: { color: t.chartAxis } },
      axisTick:  { lineStyle: { color: t.chartAxis } },
      axisLabel: { color: t.textSecondary },
      splitLine: { lineStyle: { color: t.chartGrid, type: 'dashed' } },
    },
    valueAxis: {
      axisLine:  { lineStyle: { color: t.chartAxis }, show: false },
      axisTick:  { lineStyle: { color: t.chartAxis }, show: false },
      axisLabel: { color: t.textSecondary },
      splitLine: { lineStyle: { color: t.chartGrid, type: 'dashed' } },
    },
    timeAxis: {
      axisLine:  { lineStyle: { color: t.chartAxis } },
      axisTick:  { lineStyle: { color: t.chartAxis } },
      axisLabel: { color: t.textSecondary },
      splitLine: { lineStyle: { color: t.chartGrid, type: 'dashed' } },
    },
    line: {
      smooth: false,
      lineStyle: { width: 2 },
      symbol: 'none',
      symbolSize: 6,
    },
    bar: { itemStyle: { borderRadius: [3, 3, 0, 0] } },
    grid: { left: 12, right: 12, top: 28, bottom: 28, containLabel: true },
  }
}

let registered = new Set<string>()

function registerCurrent() {
  const t = readChartTokens()
  const themeName = document.documentElement.dataset.theme === 'light' ? 'pt-light' : 'pt-dark'
  // Always re-register so token edits during dev refresh too.
  echarts.registerTheme(themeName, buildEChartsTheme(t))
  registered.add(themeName)
  return themeName
}

/**
 * React hook: returns the registered theme name plus a key that bumps when the
 * theme switches, so callers can force ECharts to re-mount with the new theme.
 */
export function useChartTheme() {
  const initial = typeof document !== 'undefined' ? registerCurrent() : 'pt-dark'
  const [themeName, setThemeName] = useState(initial)
  const [bump, setBump] = useState(0)

  useEffect(() => {
    function handler() {
      const next = registerCurrent()
      setThemeName(next)
      setBump(b => b + 1)
    }
    window.addEventListener('pt:theme-change', handler)
    return () => window.removeEventListener('pt:theme-change', handler)
  }, [])

  return { themeName, themeKey: `${themeName}-${bump}` }
}

export { echarts }
export type { EChartsOption }
