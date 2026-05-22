import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// RTL does not auto-unmount between tests under vitest — unmount + reset the
// DOM after every case so queries don't match elements left over from earlier.
afterEach(() => { cleanup() })

// Recharts probes container dimensions via ResizeObserver and ultimately
// falls back to offsetWidth/offsetHeight. jsdom returns 0 for both, which
// makes ResponsiveContainer render an empty placeholder and the inner chart
// never mounts. Stub a fixed test-time canvas of 800×400.
const TEST_W = 800
const TEST_H = 400

class ResizeObserverMock {
  private cb: ResizeObserverCallback
  constructor(cb: ResizeObserverCallback) { this.cb = cb }
  observe(target: Element) {
    // Fire once with the stubbed contentRect so recharts captures a non-zero size.
    this.cb([{
      target,
      contentRect: { x: 0, y: 0, top: 0, left: 0, bottom: TEST_H, right: TEST_W,
                     width: TEST_W, height: TEST_H, toJSON: () => ({}) } as DOMRectReadOnly,
      borderBoxSize: [], contentBoxSize: [], devicePixelContentBoxSize: [],
    } as ResizeObserverEntry], this as unknown as ResizeObserver)
  }
  unobserve() {}
  disconnect() {}
}
;(globalThis as any).ResizeObserver = ResizeObserverMock

Object.defineProperty(HTMLElement.prototype, 'offsetWidth',
  { configurable: true, get() { return TEST_W } })
Object.defineProperty(HTMLElement.prototype, 'offsetHeight',
  { configurable: true, get() { return TEST_H } })
Object.defineProperty(HTMLElement.prototype, 'clientWidth',
  { configurable: true, get() { return TEST_W } })
Object.defineProperty(HTMLElement.prototype, 'clientHeight',
  { configurable: true, get() { return TEST_H } })

// `getBBox` is what recharts uses to compute label / axis sizes.
if (typeof SVGElement !== 'undefined' && !(SVGElement.prototype as any).getBBox) {
  ;(SVGElement.prototype as any).getBBox = function () {
    return { x: 0, y: 0, width: 100, height: 16 }
  }
}
