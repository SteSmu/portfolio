import { useEffect, useRef } from 'react'
import { echarts, useChartTheme } from '../../lib/echarts'
import type { EChartsOption } from 'echarts'
import type { CSSProperties } from 'react'

type Props = {
  option: EChartsOption
  /** Pixel height; if responsive height is needed, pass it via `style` */
  height?: number
  className?: string
  style?: CSSProperties
  /** Forces a fresh chart instance (use when option.series is structurally swapped) */
  notMerge?: boolean
  /** Optional click handler — receives ECharts event params */
  onClick?: (params: unknown) => void
}

/**
 * Thin wrapper around echarts/core that:
 *  - re-initialises on theme change (registered via useChartTheme)
 *  - resizes on container width changes
 *  - disposes cleanly on unmount
 *
 * Bundle-conscious: only the chart types registered in lib/echarts.ts are
 * available. Add new chart types there, not here.
 */
export default function Chart({
  option,
  height = 320,
  className,
  style,
  notMerge = false,
  onClick,
}: Props) {
  const ref = useRef<HTMLDivElement | null>(null)
  const instRef = useRef<echarts.ECharts | null>(null)
  const { themeName, themeKey } = useChartTheme()

  // Re-initialise on theme change.
  useEffect(() => {
    if (!ref.current) return
    instRef.current?.dispose()
    const inst = echarts.init(ref.current, themeName)
    instRef.current = inst
    inst.setOption(option, true)
    if (onClick) inst.on('click', onClick)

    const ro = new ResizeObserver(() => inst.resize())
    ro.observe(ref.current)

    return () => {
      ro.disconnect()
      inst.dispose()
      instRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [themeKey])

  // Update option without re-mount when only data changes.
  useEffect(() => {
    instRef.current?.setOption(option, notMerge)
  }, [option, notMerge])

  return (
    <div
      ref={ref}
      className={className}
      style={{ width: '100%', height, ...style }}
    />
  )
}
