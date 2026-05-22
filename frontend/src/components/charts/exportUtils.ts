/**
 * Chart-panel export helpers.
 *
 * PNG: For SVG-containing panels — tight-crops via getBBox() + canvas rasterization.
 *      For HTML-only panels — html-to-image capture of the chart body (no panel chrome).
 *
 * Vector (SVG): tight-crops the inner <svg> using getBBox() so the file contains
 *      only visible content + EXPORT_PADDING on each side.  True vector, no border.
 *      For HTML-only panels falls back to compact PNG-in-PDF.
 *
 * Tight-crop: uses svgEl.getBBox() on the live DOM to get the actual rendered
 *      bounding box of all visible elements in SVG user-coordinate space, then
 *      resets viewBox to (bbox + padding) before serializing.
 *
 * CSV: caller-provided, see downloadCsv below.
 */
import { toPng } from 'html-to-image'
import jsPDF from 'jspdf'
import { buildEmbeddedFontCss } from './fontEmbed'
import { getExportPadding } from './exportSettings'

const PNG_SCALE = 2

interface ExportOptions {
  filename: string
  caption?: string
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function triggerDownload(dataUrl: string, filename: string) {
  const a = document.createElement('a')
  a.href = dataUrl
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

async function captureNodeAsPng(node: HTMLElement): Promise<string> {
  const excluded = Array.from(node.querySelectorAll<HTMLElement>('[data-export-exclude]'))
  excluded.forEach(el => {
    el.dataset.prevDisplay = el.style.display
    el.style.display = 'none'
  })

  try {
    const target = (node.firstElementChild as HTMLElement | null) ?? node
    return await toPng(target, {
      pixelRatio: PNG_SCALE,
      backgroundColor: '#FFFFFF',
      cacheBust: true,
      style: { transform: 'none' },
    })
  } finally {
    excluded.forEach(el => {
      el.style.display = el.dataset.prevDisplay ?? ''
      delete el.dataset.prevDisplay
    })
  }
}

/**
 * Convert an SVG XML string to a PNG data URL via canvas rasterization.
 * Uses a Blob URL → Image → canvas.drawImage pipeline so the SVG can reference
 * embedded fonts and filters without cross-origin issues.
 */
async function svgStringToPng(svgString: string, logicalW: number, logicalH: number): Promise<string> {
  const blob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' })
  const url  = URL.createObjectURL(blob)
  try {
    const img = await new Promise<HTMLImageElement>((resolve, reject) => {
      const i = new Image()
      i.onload  = () => resolve(i)
      i.onerror = reject
      i.src = url
    })
    const canvas = document.createElement('canvas')
    canvas.width  = logicalW  * PNG_SCALE
    canvas.height = logicalH * PNG_SCALE
    const ctx = canvas.getContext('2d')!
    ctx.fillStyle = '#FFFFFF'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
    return canvas.toDataURL('image/png')
  } finally {
    URL.revokeObjectURL(url)
  }
}

/**
 * Build a tight-cropped, font-embedded SVG string from a live <svg> element.
 *
 * Steps:
 *   1. getBBox() on the live element → true content bounding box in user units.
 *   2. Clone the element; set viewBox to (bbox + padding); explicit width/height.
 *   3. Inject @font-face rules via buildEmbeddedFontCss().
 */
async function buildExportSvg(svgEl: SVGSVGElement): Promise<{ svgString: string; w: number; h: number }> {
  const pad = getExportPadding()

  // For donut panels: [data-donut-content] group holds the tight content bbox.
  // For Recharts panels: neither the root <svg> (returns full layout box) nor
  // a single <g> child (Recharts places x-axis labels in a sibling group, so
  // one group's bbox misses them) gives the correct tight bounds.  Instead,
  // iterate every drawable element and compute the union bbox manually.
  const donutGroup = svgEl.querySelector<SVGGElement>('[data-donut-content]')
  let bbox: { x: number; y: number; width: number; height: number }

  if (donutGroup) {
    bbox = donutGroup.getBBox()
  } else {
    // Union of getBBox across all drawn primitives — captures bars, axes,
    // labels, reference lines, etc. regardless of their group hierarchy.
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
    for (const el of svgEl.querySelectorAll<SVGGraphicsElement>(
      'rect, line, text, path, circle, ellipse, polyline, polygon'
    )) {
      try {
        const b = el.getBBox()
        if (b.width === 0 && b.height === 0) continue
        if (minX > b.x)          minX = b.x
        if (minY > b.y)          minY = b.y
        if (maxX < b.x + b.width)  maxX = b.x + b.width
        if (maxY < b.y + b.height) maxY = b.y + b.height
      } catch { /* element not renderable */ }
    }
    bbox = isFinite(minX)
      ? { x: minX, y: minY, width: maxX - minX, height: maxY - minY }
      : { x: 0, y: 0, width: 0, height: 0 }
  }

  const origVb     = svgEl.viewBox.baseVal
  const hasContent = bbox.width > 0 && bbox.height > 0
  const cropX = hasContent ? bbox.x      - pad : origVb.x
  const cropY = hasContent ? bbox.y      - pad : origVb.y
  const cropW = hasContent ? bbox.width  + pad * 2 : origVb.width
  const cropH = hasContent ? bbox.height + pad * 2 : origVb.height

  const clone = svgEl.cloneNode(true) as SVGSVGElement
  clone.setAttribute('xmlns',   'http://www.w3.org/2000/svg')
  clone.setAttribute('viewBox', `${cropX} ${cropY} ${cropW} ${cropH}`)
  // No explicit width/height: the browser/Inkscape derives the display size
  // from the viewBox aspect ratio and scales the SVG to fill the viewer —
  // identical to the donut export approach.  With explicit dimensions set to
  // cropW×cropH the Recharts SVG would render at that fixed pixel size;
  // because getBBox() on the root <svg> returns the full SVG layout box
  // (including internal Recharts margins), cropH > actual content height,
  // which causes whitespace below the chart in SVG viewers.
  clone.removeAttribute('width')
  clone.removeAttribute('height')
  clone.removeAttribute('style')

  // Inject embedded @font-face rules.
  const embeddedFonts = await buildEmbeddedFontCss()
  const style = document.createElementNS('http://www.w3.org/2000/svg', 'style')
  // Single-quoted font names are required inside CSS strings embedded in SVG
  // <style> elements so XMLSerializer produces well-formed XML.
  style.textContent = embeddedFonts
    + "\ntext, tspan { font-family: 'Source Sans 3', system-ui, sans-serif; }"
  clone.insertBefore(style, clone.firstChild)

  const svgString = new XMLSerializer().serializeToString(clone)

  // Validate before returning — catches any remaining serialization bugs
  // (mangled attributes, broken entities) before they produce broken files.
  const parsed = new DOMParser().parseFromString(svgString, 'image/svg+xml')
  const parseError = parsed.querySelector('parsererror')
  if (parseError) {
    throw new Error(`SVG serialization produced invalid XML: ${parseError.textContent?.slice(0, 200)}`)
  }

  return { svgString, w: cropW, h: cropH }
}

// ── Public API ────────────────────────────────────────────────────────────────

export async function exportPanelAsPng(node: HTMLElement, opts: ExportOptions) {
  const svgEl = node.querySelector<SVGSVGElement>('svg')
  if (svgEl) {
    // SVG-containing panel: tight-crop via getBBox() + canvas PNG.
    const { svgString, w, h } = await buildExportSvg(svgEl)
    const dataUrl = await svgStringToPng(svgString, w, h)
    triggerDownload(dataUrl, `${opts.filename}.png`)
  } else {
    // HTML-only panel (TopVenuesPanel, SearchMetricsPanel): existing html-to-image path.
    const dataUrl = await captureNodeAsPng(node)
    triggerDownload(dataUrl, `${opts.filename}.png`)
  }
}

/**
 * Vector export for chart panels.
 *
 * Donut panels: crop is computed from the pre-computed data-content-* attributes
 * (SVG user-space coordinates set at generation time) to avoid a getBBox()
 * CSS-scaling artefact where width:100% causes getBBox to return pixel values
 * instead of user-coordinate values, producing a crop that is too large with
 * content in the top-left corner.
 *
 * Other SVG panels (Recharts): use the standard buildExportSvg/getBBox path.
 * HTML-only panels: compact PNG-in-PDF (page sized to content, no A4 margins).
 */
export async function exportPanelAsPdf(node: HTMLElement, opts: ExportOptions) {
  const svgEl = node.querySelector<SVGSVGElement>('svg')
  if (svgEl) {
    // Donut SVGs carry data-content-* bounds in guaranteed SVG user coordinates.
    // Use them for the SVG download to avoid the getBBox CSS-scale artefact.
    const svgString = isFinite(parseFloat(svgEl.getAttribute('data-content-x') ?? ''))
      ? await buildDonutSvgDownload(svgEl)
      : (await buildExportSvg(svgEl)).svgString
    const blob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' })
    const url  = URL.createObjectURL(blob)
    triggerDownload(url, `${opts.filename}.svg`)
    URL.revokeObjectURL(url)
    return
  }
  await exportCompactPdf(node, opts)
}

/**
 * Build an SVG download string for donut panels using data-content-* attributes.
 * These hold the tight content bounds in SVG user coordinates (computed at
 * generation time), bypassing getBBox which returns CSS-pixel-scaled values
 * when the live SVG has width:100% applied.
 */
async function buildDonutSvgDownload(svgEl: SVGSVGElement): Promise<string> {
  const pad = getExportPadding()
  const cx  = parseFloat(svgEl.getAttribute('data-content-x') ?? '')
  const cy  = parseFloat(svgEl.getAttribute('data-content-y') ?? '')
  const cw  = parseFloat(svgEl.getAttribute('data-content-w') ?? '')
  const ch  = parseFloat(svgEl.getAttribute('data-content-h') ?? '')

  const cropX = cx - pad
  const cropY = cy - pad
  const cropW = cw + pad * 2
  const cropH = ch + pad * 2

  const clone = svgEl.cloneNode(true) as SVGSVGElement
  clone.setAttribute('xmlns',   'http://www.w3.org/2000/svg')
  clone.setAttribute('viewBox', `${cropX} ${cropY} ${cropW} ${cropH}`)
  // No explicit width/height: the browser/Inkscape scales the SVG to fill
  // the viewer window while maintaining aspect ratio.  With explicit px
  // dimensions the file renders at ~300px in a wide browser window, making
  // the chart appear in the top-left with white space everywhere else.
  clone.removeAttribute('width')
  clone.removeAttribute('height')
  clone.removeAttribute('style')

  const embeddedFonts = await buildEmbeddedFontCss()
  const style = document.createElementNS('http://www.w3.org/2000/svg', 'style')
  style.textContent = embeddedFonts
    + "\ntext, tspan { font-family: 'Source Sans 3', system-ui, sans-serif; }"
  clone.insertBefore(style, clone.firstChild)

  const svgString = new XMLSerializer().serializeToString(clone)
  const parsed    = new DOMParser().parseFromString(svgString, 'image/svg+xml')
  const parseErr  = parsed.querySelector('parsererror')
  if (parseErr) throw new Error(`SVG serialization error: ${parseErr.textContent?.slice(0, 200)}`)
  return svgString
}

async function exportCompactPdf(node: HTMLElement, opts: ExportOptions) {
  const dataUrl = await captureNodeAsPng(node)
  const img = new Image()
  await new Promise<void>((resolve, reject) => {
    img.onload  = () => resolve()
    img.onerror = (e) => reject(e)
    img.src = dataUrl
  })

  const pxPerMm = 72 / 25.4
  const imgWmm  = (img.naturalWidth  / PNG_SCALE) / pxPerMm
  const imgHmm  = (img.naturalHeight / PNG_SCALE) / pxPerMm

  const pdf = new jsPDF({
    unit:        'mm',
    format:      [imgWmm, imgHmm],
    orientation: imgWmm >= imgHmm ? 'landscape' : 'portrait',
  })
  pdf.addImage(dataUrl, 'PNG', 0, 0, imgWmm, imgHmm, undefined, 'FAST')

  if (opts.caption) {
    pdf.setFont('times', 'italic')
    pdf.setFontSize(9)
    pdf.setTextColor(85, 85, 85)
    const wrapped = pdf.splitTextToSize(opts.caption, imgWmm)
    pdf.text(wrapped, imgWmm / 2, imgHmm - 4, { align: 'center' })
  }

  pdf.save(`${opts.filename}.pdf`)
}

/** CSV download — no dependency needed. */
export function downloadCsv(
  filename: string,
  headers: string[],
  rows: (string | number | null)[][],
) {
  const escape = (v: string | number | null) => `"${String(v ?? '').replace(/"/g, '""')}"`
  const lines = [headers.map(escape).join(','), ...rows.map(r => r.map(escape).join(','))]
  const blob = new Blob([lines.join('\r\n')], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
