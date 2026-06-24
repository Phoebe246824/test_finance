# Sentinel Edge Design System

## 1. Atmosphere & Identity

Sentinel Edge feels like a quiet financial risk command center: dense, operational, and calm under pressure. The signature is pale blue operational glass with compact panels, strong numeric hierarchy, and restrained risk-state color.

## 2. Color

### Palette

| Role | Token | Light | Dark | Usage |
|------|-------|-------|------|-------|
| Surface/page | `--page-bg` | `#eaf2ff` | N/A | App shell background |
| Surface/panel | `--panel` | `#ffffff` | N/A | Cards, form panels, tables |
| Surface/soft | `--panel-soft` | `#f7fbff` | N/A | Summary blocks and subtle nested areas |
| Surface/control | `--control-soft` | `#eef5ff` | N/A | Icon controls and calm progress surfaces |
| Surface/progress-track | `--progress-track` | `#dfeaff` | N/A | Pipeline progress track |
| Surface/error-soft | `--danger-soft` | `#fff0f0` | N/A | Failed task and form error backgrounds |
| Text/primary | `--text` | `#10213d` | N/A | Body, headings, table values |
| Text/secondary | `--muted` | `#65758c` | N/A | Metadata and helper text |
| Text/info | `--info-text` | `#456176` | N/A | Progress detail and quiet operational notes |
| Accent/primary | `--primary` | `#1f65e5` | N/A | Primary buttons, active progress, links |
| Accent/deep | `--primary-deep` | `#0f3473` | N/A | Sidebar depth and strong headings |
| Border/default | `--line` | `#d7e4f4` | N/A | Panel borders and major dividers |
| Border/subtle | `--line-soft` | `#e7eef8` | N/A | Inner dividers and table frames |
| Border/error | `--danger-line` | `#f2bdc0` | N/A | Failed task and form error borders |
| Status/error | `--danger` | `#ed3434` | N/A | Error text and high risk |
| Status/warning | `--warning` | `#f3a917` | N/A | Medium risk and caution |
| Status/success | `--success` | `#1ca66a` | N/A | Low risk and completed states |

### Rules

- Operational surfaces use white or soft blue; avoid decorative gradients beyond the app shell.
- Risk color is semantic only: red for high, amber for medium, green for low or complete.
- New colors must be promoted to a token before UI code uses them.

## 3. Typography

### Scale

| Level | Size | Weight | Line Height | Tracking | Usage |
|-------|------|--------|-------------|----------|-------|
| Page title | 28px | 900 | 1.2 | 0 | View headers |
| Section title | 16px | 800 | 1.35 | 0 | Panel headings |
| Card title | 15px | 800 | 1.35 | 0 | Compact card headings |
| Metric value | 21px | 900 | 1.2 | 0 | KPI values |
| Body | 14px | 400-700 | 1.5 | 0 | Default UI text |
| Caption | 12px | 700-850 | 1.4 | 0 | Metadata, labels, progress detail |

### Font Stack

- Primary: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif.
- Mono: browser default monospace only for exported code or diagnostics.

### Rules

- Compact panels favor 12-16px text; large display type is reserved for page headers.
- Letter spacing stays at 0 except where existing uppercase labels require tighter metadata treatment.

## 4. Spacing & Layout

### Base Unit

All spacing derives from 4px.

| Token | Value | Usage |
|-------|-------|-------|
| `--space-1` | 4px | Fine inner gaps |
| `--space-2` | 8px | Grid gaps, table frames, compact panels |
| `--space-3` | 12px | Field padding, button groups |
| `--space-4` | 16px | Panel padding |
| `--space-5` | 20px | Header horizontal padding |
| `--space-6` | 24px | Major card spacing |
| `--space-8` | 32px | Wide section rhythm |

### Grid

- Main shell: 232px sidebar plus flexible content.
- Analysis view: two-column work surface above 1100px, single-column below.
- Tables and panels use 8px radius and 8px grid gaps.

### Rules

- Keep operational panels dense but scannable.
- Avoid nested cards; framed panels are allowed for tools, summaries, and repeated table rows.

## 5. Components

### Panel

- Structure: `.panel.stack` wraps a section title, content, and controls.
- Spacing: 16px padding, 8-12px internal gaps.
- States: static surface with subtle border and shadow.
- Accessibility: headings stay semantic and visible.

### Button

- Structure: `.button` and `.button.secondary`.
- Spacing: compact inline controls with 8px radius.
- States: hover, disabled, and loading text must preserve button width closely enough to avoid layout jump.
- Accessibility: use real `<button>` elements for commands.

### Risk Badge

- Structure: `.risk-badge` plus semantic risk class.
- Variants: high, medium, low, unknown, pending.
- Accessibility: text label is always visible, color is supporting information only.

### Pipeline Progress

- Structure: `.progress-card` containing metadata row, track, fill, and detail text.
- Variants: single analysis and batch analysis.
- Spacing: 12px padding, 8px gap, 8px radius.
- States: queued, running, success, failed; failed uses danger token, success uses success token.
- Accessibility: visible stage text and numeric progress accompany the visual track.

## 6. Motion & Interaction

### Timing

| Type | Duration | Easing | Usage |
|------|----------|--------|-------|
| Micro | 120ms | ease-out | Button hover and active states |
| Standard | 200ms | ease-in-out | Progress fill changes |

### Rules

- Animate only opacity and transform when motion is needed.
- Progress updates may transition width because it is a small, bounded indicator, not page layout.
- Respect compact layout; no decorative motion in operational screens.

## 7. Depth & Surface

### Strategy

Mixed, matching the existing app: thin borders define structure, and a single soft shadow separates primary panels from the page.

| Level | Value | Usage |
|-------|-------|-------|
| Panel shadow | `--shadow` | Main cards and panels |
| Default border | `1px solid var(--line)` | Panel frame |
| Subtle border | `1px solid var(--line-soft)` | Nested summaries, tables, progress |
