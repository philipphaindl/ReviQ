/**
 * Visual-regression loop for donut chart layout.
 *
 * Precondition: frontend is serving at http://localhost:3000 (Docker).
 * The test injects fake taxonomy paper data via page.route() so the
 * donut charts render without needing real extraction data in the DB.
 *
 * Failure thresholds (tune in one place):
 */
import { test, expect, type Page } from '@playwright/test'
import * as fs   from 'fs'
import * as path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

const PID             = 2
const SS_DIR          = path.join(__dirname, 'screenshots')
const MIN_WIDTH_RATIO  = 0.50   // SVG width / card width
const MIN_HEIGHT_RATIO = 0.60   // SVG height / card height
const MAX_H_OFFSET_PX  = 40    // |svg_center_x - card_center_x|

// Fake papers — enough to produce two non-trivial donut charts.
const FAKE_PAPERS = [
  { paper_id: 1, citekey: 'S001', title: 'P1', values: { research_type: 'Evaluation Research',  contribution_type: 'Tool'      }, filled: 2, total_fields: 2 },
  { paper_id: 2, citekey: 'S002', title: 'P2', values: { research_type: 'Evaluation Research',  contribution_type: 'Tool'      }, filled: 2, total_fields: 2 },
  { paper_id: 3, citekey: 'S003', title: 'P3', values: { research_type: 'Solution Proposal',    contribution_type: 'Method'    }, filled: 2, total_fields: 2 },
  { paper_id: 4, citekey: 'S004', title: 'P4', values: { research_type: 'Philosophical Paper',  contribution_type: 'Tool'      }, filled: 2, total_fields: 2 },
  { paper_id: 5, citekey: 'S005', title: 'P5', values: { research_type: 'Solution Proposal',    contribution_type: 'Framework' }, filled: 2, total_fields: 2 },
  { paper_id: 6, citekey: 'S006', title: 'P6', values: { research_type: 'Evaluation Research',  contribution_type: 'Method'    }, filled: 2, total_fields: 2 },
]

// ── Helpers ────────────────────────────────────────────────────────────────

async function setupAndNavigate(page: Page) {
  fs.mkdirSync(SS_DIR, { recursive: true })

  // 1. Set project in localStorage before the page loads
  await page.addInitScript((pid) => {
    localStorage.setItem('reviq_project_id', String(pid))
  }, PID)

  // 2. Mock extraction-summary to inject taxonomy paper data
  await page.route(`**/projects/${PID}/extraction-summary`, async route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ fields: [], papers: FAKE_PAPERS }),
    })
  )

  // 3. Navigate → click Charts tab → wait for first donut SVG
  await page.goto('http://localhost:3000/results')
  await page.click('button:has-text("Charts")')
  await page.waitForSelector('svg[role="img"]', { timeout: 15_000 })
  // Give React Query a moment to settle all requests
  await page.waitForTimeout(800)
}

async function saveSS(page: Page, name: string) {
  await page.screenshot({ path: path.join(SS_DIR, `${name}.png`), fullPage: false })
}

// ── Tests ──────────────────────────────────────────────────────────────────

test.describe('Donut chart layout', () => {

  // ── 1. Structural: no recharts-wrapper ─────────────────────────────────
  test('donut SVG parent is NOT recharts-wrapper', async ({ page }) => {
    await setupAndNavigate(page)
    await saveSS(page, '01-before-recharts-check')

    const parentClasses: string[] = await page.evaluate(() =>
      Array.from(document.querySelectorAll('svg[role="img"]'))
        .map(s => s.parentElement?.className ?? '')
    )

    console.log('donut parent classes:', parentClasses)
    expect(parentClasses.length, 'expected at least one donut SVG').toBeGreaterThan(0)

    for (const cls of parentClasses) {
      expect(cls).not.toContain('recharts-wrapper')
    }
  })

  // ── 2. Geometry: SVG is square (not squashed) ───────────────────────────
  test('donut SVG has ~1:1 aspect ratio', async ({ page }) => {
    await setupAndNavigate(page)
    await saveSS(page, '02-before-aspect-ratio')

    const donuts = await page.locator('svg[role="img"]').all()
    expect(donuts.length).toBeGreaterThan(0)
    console.log(`found ${donuts.length} donut SVG(s)`)

    for (const [i, donut] of donuts.entries()) {
      const box = await donut.boundingBox()
      if (!box) { console.warn(`donut ${i}: no bounding box`); continue }

      console.log(`donut ${i}: ${box.width.toFixed(0)}×${box.height.toFixed(0)}`)
      const ratio = box.width / box.height
      expect(ratio, `donut ${i} aspect ratio`).toBeGreaterThan(0.80)
      expect(ratio, `donut ${i} aspect ratio`).toBeLessThan(1.20)
    }
  })

  // ── 3. Coverage: SVG fills enough of the card ───────────────────────────
  test('donut SVG fills at least 50% of card width and 60% of card height', async ({ page }) => {
    await setupAndNavigate(page)
    await saveSS(page, '03-before-coverage')

    const cards = await page.locator('section:has(svg[role="img"])').all()
    expect(cards.length, 'expected at least one card with a donut').toBeGreaterThan(0)
    console.log(`found ${cards.length} donut card(s)`)

    for (const [i, card] of cards.entries()) {
      const cardBox = await card.boundingBox()
      const svgBox  = await card.locator('svg[role="img"]').first().boundingBox()
      if (!cardBox || !svgBox) { console.warn(`card ${i}: missing bounding box`); continue }

      const wRatio = svgBox.width  / cardBox.width
      const hRatio = svgBox.height / cardBox.height
      console.log(`card ${i}: SVG ${svgBox.width.toFixed(0)}×${svgBox.height.toFixed(0)} in card ${cardBox.width.toFixed(0)}×${cardBox.height.toFixed(0)} (w=${(wRatio*100).toFixed(0)}% h=${(hRatio*100).toFixed(0)}%)`)

      expect(wRatio, `card ${i} SVG width/card width`).toBeGreaterThanOrEqual(MIN_WIDTH_RATIO)
      expect(hRatio, `card ${i} SVG height/card height`).toBeGreaterThanOrEqual(MIN_HEIGHT_RATIO)
    }
  })

  // ── 4. Centering: SVG is horizontally centered in its card ──────────────
  test('donut SVG is horizontally centered in its card', async ({ page }) => {
    await setupAndNavigate(page)
    await saveSS(page, '04-before-centering')

    const cards = await page.locator('section:has(svg[role="img"])').all()

    for (const [i, card] of cards.entries()) {
      const cardBox = await card.boundingBox()
      const svgBox  = await card.locator('svg[role="img"]').first().boundingBox()
      if (!cardBox || !svgBox) continue

      const svgCx  = svgBox.x  + svgBox.width  / 2
      const cardCx = cardBox.x + cardBox.width  / 2
      const offset = Math.abs(svgCx - cardCx)
      console.log(`card ${i}: horizontal offset = ${offset.toFixed(1)}px`)
      expect(offset, `card ${i} horizontal centering offset`).toBeLessThan(MAX_H_OFFSET_PX)
    }
  })
})
