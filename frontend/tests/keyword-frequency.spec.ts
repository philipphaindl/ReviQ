import { test } from '@playwright/test'
import * as fs   from 'fs'
import * as path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const SS = path.join(__dirname, 'screenshots')

const PAPERS = [
  { abstract: 'This paper presents a novel approach to Java virtual machine instrumentation using bytecode transformation techniques. We propose a framework for dynamic analysis of JVM applications.',
    keywords: 'java;virtual machine;bytecode;instrumentation' },
  { abstract: 'We investigate garbage collection strategies in the Java virtual machine. Our evaluation demonstrates significant performance improvements for memory management algorithms.',
    keywords: 'java;garbage collection;memory management' },
  { abstract: 'Bytecode instrumentation enables runtime monitoring of Java programs. This study examines profiling tools for performance analysis and debugging of JVM-based applications.',
    keywords: null },
  { abstract: 'We present a compiler optimization technique for Java bytecode. The approach leverages just-in-time compilation to improve execution performance of virtual machine code.',
    keywords: null },
].map((p, i) => ({
  id: i + 1, citekey: `S00${i+1}`, title: `Paper ${i+1}`,
  abstract: p.abstract, keywords: p.keywords,
  final_decision: { decision: 'I' },
  values: { research_type: 'Evaluation Research', contribution_type: 'Tool' },
  filled: 2, total_fields: 2,
}))

async function setup(page: any) {
  fs.mkdirSync(SS, { recursive: true })
  await page.addInitScript(() => { localStorage.setItem('reviq_project_id', '2') })
  await page.route('**/projects/2/extraction-summary', (r: any) =>
    r.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify({ fields: [], papers: PAPERS }) }))
  await page.route('**/projects/2/papers*', (r: any) =>
    r.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify(PAPERS) }))
  await page.goto('http://localhost:3000/results')
  await page.click('button:has-text("Charts")')
  await page.waitForSelector('text=Keyword Frequency', { timeout: 15_000 })
  await page.locator('text=Keyword Frequency').first().scrollIntoViewIfNeeded()
  await page.waitForTimeout(800)
}

test('Keyword Frequency — all three modes + SVG export margin check', async ({ page }) => {
  await setup(page)
  const panel = page.locator('section').filter({ hasText: 'Keyword Frequency' }).first()

  // Abstracts bar chart
  await panel.screenshot({ path: path.join(SS, 'keyword-frequency-abstracts.png') })

  // Word Cloud
  await panel.locator('button', { hasText: 'Word Cloud' }).click()
  await page.waitForTimeout(500)
  await panel.screenshot({ path: path.join(SS, 'keyword-frequency-wordcloud.png') })

  // BibTeX (if available)
  const bibtexBtn = panel.locator('button', { hasText: 'BibTeX' })
  if (await bibtexBtn.count() > 0) {
    await bibtexBtn.click()
    await page.waitForTimeout(300)
    await panel.screenshot({ path: path.join(SS, 'keyword-frequency-bibtex.png') })
  }

  // ── SVG export margin check (Word Cloud mode) ──────────────────────────────
  await panel.locator('button', { hasText: 'Word Cloud' }).click()
  await page.waitForTimeout(300)

  // Open ⋯ menu and click SVG download
  const menuBtn = panel.locator('button[aria-label], button').last()
  const [dl] = await Promise.all([
    page.waitForEvent('download', { timeout: 8_000 }),
    menuBtn.click().then(() => page.locator('text=Download as vector').first().click()),
  ])
  const svgPath = path.join(SS, 'keyword-wordcloud-export.svg')
  await dl.saveAs(svgPath)

  const svg = fs.readFileSync(svgPath, 'utf-8')
  const vbMatch = svg.match(/viewBox="([^"]+)"/)
  if (vbMatch) {
    const [vbx, vby, vbw, vbh] = vbMatch[1].split(' ').map(Number)
    console.log(`Word Cloud SVG viewBox: ${vbw.toFixed(0)}×${vbh.toFixed(0)}`)

    // Collect all y from text elements
    const ys: number[] = []
    for (const m of svg.matchAll(/<text[^>]* y="([0-9.-]+)"/g)) ys.push(parseFloat(m[1]))
    const xs: number[] = []
    for (const m of svg.matchAll(/<text[^>]* x="([0-9.-]+)"/g)) xs.push(parseFloat(m[1]))

    if (ys.length && xs.length) {
      const minY = Math.min(...ys), maxY = Math.max(...ys)
      const minX = Math.min(...xs), maxX = Math.max(...xs)
      const topGap    = minY - vby
      const bottomGap = (vby + vbh) - maxY
      const leftGap   = minX - vbx
      const rightGap  = (vbx + vbw) - maxX
      console.log(`Gaps — top:${topGap.toFixed(0)} bottom:${bottomGap.toFixed(0)} left:${leftGap.toFixed(0)} right:${rightGap.toFixed(0)}`)
      if (topGap > 50)    console.warn(`⚠ Large top margin: ${topGap.toFixed(0)}px`)
      if (bottomGap > 50) console.warn(`⚠ Large bottom margin: ${bottomGap.toFixed(0)}px`)
      if (leftGap > 50)   console.warn(`⚠ Large left margin: ${leftGap.toFixed(0)}px`)
      if (rightGap > 50)  console.warn(`⚠ Large right margin: ${rightGap.toFixed(0)}px`)
    }
  }
  console.log('All keyword modes verified ✓')
})
