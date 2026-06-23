// Thin TypeScript wrapper around the shared canvas algorithms in
// shared-design/glyph.js — see that file for the actual implementations
// (kept there so design-doc.html and this app share the same pixels).
//
// The Vite alias @shared → ../shared-design (see mvp/vite.config.ts) makes
// the import below resolve at build time without copying the source.

// @ts-expect-error — shared-design has no .d.ts; types are declared in this wrapper.
import * as Glyph from '@shared/glyph.js';

export type GlyphOpts = {
  seed: number;
  p1?: number; p2?: number; p3?: number; p4?: number; p5?: number;
  palette?: string;
  cell?: number;
  bg?: string;
  mode?: 'noise' | 'waves' | 'mandala';
  radial?: boolean;
  rays?: number;
};

export const strHash: (s: string) => number = Glyph.strHash;
export const pickStyle: (seed: number, opts?: Partial<GlyphOpts>) => Partial<GlyphOpts> = Glyph.pickStyle;
export const renderGlyph: (canvas: HTMLCanvasElement, opts: GlyphOpts) => void = Glyph.renderGlyph;
