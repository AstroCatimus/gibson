/**
 * Gibson Design System
 * "The Shop After Hours" — warm bookstore at night.
 * All screens import from here; no colour literals scattered in files.
 */

// ── Palette ──────────────────────────────────────────────────────
export const C = {
  // Backgrounds (warm dark browns — like aged walnut shelves)
  bg:      '#13110e',   // deepest background
  surface: '#1c1814',   // raised surface
  card:    '#221e19',   // card background
  border:  '#2e2820',   // default border

  // Accent — amber gold (aged book spine, candlelight)
  accent:    '#c8902e',
  accentDim: '#8a611f',
  accentBg:  '#2d1e08',

  // Status
  green:    '#6aa87a',  // sage — verified, success
  greenBg:  '#0f2418',
  yellow:   '#c8a040',  // warm amber — warning
  yellowBg: '#2a1e08',
  red:      '#c05040',  // terracotta — error, delete
  redBg:    '#2a0f0a',
  blue:     '#6b9ab8',  // steel — info
  blueBg:   '#0f1e2a',
  purple:   '#9a7ab8',  // muted lavender
  purpleBg: '#1e1228',

  // Text (warm parchment tones)
  text:   '#e8dcc8',   // primary — warm off-white
  text2:  '#9a8f7a',   // secondary — muted warm gray
  text3:  '#5c5448',   // tertiary — very muted
  white:  '#fff',
};

// ── Condition colours ────────────────────────────────────────────
export const COND_COLOR = {
  'Fine':       '#7ab87a',
  'Very Good+': '#6aa870',
  'Very Good':  '#6b9ab8',
  'Good+':      '#9a7ab8',
  'Good':       '#c8902e',
  'Fair':       '#c8a040',
  'Poor':       '#c05040',
};

// ── Typography scale ─────────────────────────────────────────────
export const TYPE = {
  xs:   10,
  sm:   12,
  base: 14,
  md:   15,
  lg:   17,
  xl:   20,
  xxl:  24,
  h1:   28,
};

// ── Spacing ──────────────────────────────────────────────────────
export const SP = {
  xs:  4,
  sm:  8,
  md:  12,
  lg:  16,
  xl:  20,
  xxl: 28,
};

// ── Radius ───────────────────────────────────────────────────────
export const R = {
  sm:  6,
  md:  10,
  lg:  14,
  xl:  20,
  full: 999,
};
