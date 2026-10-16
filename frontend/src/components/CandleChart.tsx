// SVG candle chart with N1, N2… news labels on the candle where each story hit (ported from the prototype).
import { useEffect, useMemo, useRef, useState } from 'react';
import { TEXT_PX, useUi } from '@/data/ui';
import { dirColor, fmt } from '@/lib/format';
import { useT } from '@/i18n';
import type { Bar, Mkt, WireEvent } from '@/lib/types';

const H = 280, TOP = 46, PLOT = 204, PER_CANDLE = 2;
const TZ: Record<Mkt, string> = { US: 'America/New_York', CN: 'Asia/Shanghai', HK: 'Asia/Hong_Kong' };

export interface ChartItem { key: string; label: string; ev?: WireEvent; dir: number; date: string; hm: string }

function localParts(ms: number, tz: string) {
  const f = new Intl.DateTimeFormat('en-CA', { timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).formatToParts(ms);
  const g = (k: string) => f.find((p) => p.type === k)?.value || '';
  return { date: `${g('year')}-${g('month')}-${g('day')}`, hm: `${g('hour') === '24' ? '00' : g('hour')}:${g('minute')}` };
}

export function eventDir(e: WireEvent, secId?: string): number {
  if (secId && e.ai?.dirs && secId in e.ai.dirs) return Math.sign(e.ai.dirs[secId] || 0);
  const s = e.ai?.sentiment;
  return s === 'bullish' ? 1 : s === 'bearish' ? -1 : 0;
}

export function toItems(events: WireEvent[], mkt: Mkt, secId?: string): ChartItem[] {
  return [...events].sort((a, b) => b.ts - a.ts).map((ev, i) => {
    const p = localParts(ev.ts, TZ[mkt]);
    return { key: ev.id, label: 'N' + (i + 1), ev, dir: eventDir(ev, secId), date: p.date, hm: p.hm };
  });
}

export function CandleChart({ bars, unit, mkt, items, selected, onSelect, log = false }: {
  bars: Bar[]; unit: string; mkt: Mkt; items: ChartItem[]; selected: string | null; onSelect: (k: string) => void; log?: boolean;
}) {
  const upDown = useUi((s) => s.upDown);
  const fs = Math.round(TEXT_PX[useUi((s) => s.textSize)] * 0.8125);   // 13px at the medium text size
  const lw = Math.round(fs * 2.3), lh = Math.round(fs * 1.45);
  const { lang } = useT();
  const box = useRef<HTMLDivElement>(null);
  const [W, setW] = useState(740);   // draw at the real pixel width so text keeps its size
  useEffect(() => {
    if (!box.current) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(320, Math.round(e.contentRect.width))));
    ro.observe(box.current);
    return () => ro.disconnect();
  }, []);
  const model = useMemo(() => {
    const n = bars.length;
    if (!n) return null;
    const f = (v: number) => (log ? Math.log10(Math.max(v, 1e-6)) : v);   // log scale for the since-listing view
    const mn = Math.min(...bars.map((b) => f(b.l))), mx = Math.max(...bars.map((b) => f(b.h)));
    const Y = (v: number) => TOP + (1 - (f(v) - mn) / (mx - mn || 1)) * PLOT;
    const slot = W / n, bw = Math.max(1.2, slot * 0.62);
    const candles = bars.map((k, i) => {
      const x = slot * i + slot / 2, y1 = Y(Math.max(k.o, k.c)), y2 = Y(Math.min(k.o, k.c));
      return { x, hi: Y(k.h), lo: Y(k.l), bx: x - bw / 2, bw, by: y1, bh: Math.max(1, y2 - y1), dir: Math.sign(k.c - k.o) };
    });
    const boxes: [number, number][] = [];
    const markers: { key: string; label: string; x: number; ly: number; cx: number; cy: number; dir: number }[] = [];
    // Which candle each story hit.
    const hits: { it: ChartItem; idx: number }[] = [];
    for (const it of items) {
      let idx = -1;
      if (unit === 'i') {
        const bucket = it.hm.slice(0, 3) + String(Math.floor(+it.hm.slice(3) / 10) * 10).padStart(2, '0');
        idx = bars.findIndex((b) => b.t >= bucket);
      } else if (it.date >= bars[0].t.slice(0, 10) && it.date <= bars[n - 1].t.slice(0, 10)) {
        idx = bars.findIndex((b) => b.t.slice(0, 10) >= it.date);
      } else if (it.date > bars[n - 1].t.slice(0, 10) &&
                 Date.parse(it.date) - Date.parse(bars[n - 1].t.slice(0, 10)) <= 4 * 86400_000) {
        idx = n - 1;   // news since the last close (overnight, weekend) sits on the latest candle
      }
      if (idx >= 0) hits.push({ it, idx });
    }
    // At most PER_CANDLE labels per candle, highest impact first (the selected story always shows);
    // the rest stay in the event list. Otherwise a busy news day buries the candles under labels.
    const imp = (h: { it: ChartItem }) => (h.it.key === selected ? 99 : h.it.ev?.impact ?? 0);
    const byCandle = new Map<number, typeof hits>();
    for (const h of hits) byCandle.set(h.idx, [...(byCandle.get(h.idx) || []), h]);
    const shown = [...byCandle.values()].flatMap((g) => [...g].sort((x, y) => imp(y) - imp(x)).slice(0, PER_CANDLE));
    for (const { it, idx } of shown) {
      const cx = slot * idx + slot / 2, top = Y(bars[idx].h);
      const xMin = lw / 2 + 1, xMax = W - lw / 2 - 1;
      const free = (x: number, y: number) => !boxes.some(([bx, by]) => Math.abs(bx - x) < lw + 4 && Math.abs(by - y) < lh + 4);
      // Stack upward from the candle first; when the column is full, step sideways (left first, since the
      // newest candles sit at the right edge) and draw a leader line back to the candle.
      let spot: [number, number] | null = null;
      for (let k = 0; k <= 8 && !spot; k++) {
        for (const side of k ? [-1, 1] : [0]) {
          const x = Math.min(xMax, Math.max(xMin, cx + side * k * (lw + 4)));
          if (k && Math.abs(x - cx) < k * (lw + 4) * 0.5) continue;   // clamped back onto a column already tried
          for (let y = Math.max(2, top - 25); y >= 2 && !spot; y -= lh + 4) if (free(x, y)) spot = [x, y];
          if (spot) break;
        }
      }
      if (!spot) continue;   // no room left: the event stays in the list, just without a chart label
      boxes.push(spot);
      markers.push({ key: it.key, label: it.label, x: spot[0], ly: spot[1], cx, cy: top, dir: it.dir });
    }
    const grid = [0, 1 / 3, 2 / 3, 1].map((g) => { const raw = mn + (mx - mn) * g; const v = log ? 10 ** raw : raw; return { y: Y(v), label: fmt(v, v > 1000 ? 0 : v < 1 ? 3 : 2) }; });
    const lab = (k: string) => unit === 'i' ? k : new Date(k.slice(0, 10) + 'T12:00:00Z').toLocaleDateString(lang === 'zh' ? 'zh-CN' : 'en-GB',
      unit === 'm' ? (log ? { year: 'numeric', timeZone: 'UTC' } : { month: 'short', year: '2-digit', timeZone: 'UTC' }) : { day: 'numeric', month: 'short', timeZone: 'UTC' });
    const ticks = [0, 1, 2, 3, 4].map((j) => { const i = Math.round((j * (n - 1)) / 4); return { x: j === 0 ? 2 : j === 4 ? W - 2 : slot * i + slot / 2, anchor: j === 0 ? 'start' : j === 4 ? 'end' : 'middle', label: lab(bars[i].t) }; });
    return { candles, markers, grid, ticks };
  }, [bars, unit, items, selected, lang, W, lw, lh, log]);

  if (!model) return <div ref={box} />;
  return (
    <div ref={box} className="w-full">
    <svg width={W} height={H + fs + 10} viewBox={`0 0 ${W} ${H + fs + 10}`} className="block" role="img">
      {model.grid.map((g, i) => (
        <g key={i}>
          <line x1={0} x2={W} y1={g.y} y2={g.y} stroke="rgb(var(--line2))" />
          <text x={4} y={g.y - 4} textAnchor="start" fontSize={fs} fill="rgb(var(--faint))" fontFamily="IBM Plex Mono">{g.label}</text>
        </g>
      ))}
      {model.candles.map((c, i) => {
        const col = dirColor(c.dir, mkt, upDown);
        return (
          <g key={i}>
            <line x1={c.x} x2={c.x} y1={c.hi} y2={c.lo} stroke={col} strokeWidth={1} />
            <rect x={c.bx} y={c.by} width={c.bw} height={c.bh} fill={col} />
          </g>
        );
      })}
      {model.markers.map((m) => {
        const col = dirColor(m.dir, mkt, upDown);
        const sel = selected === m.key;
        return (
          <g key={m.key} onClick={() => onSelect(m.key)} style={{ cursor: 'pointer' }}>
            {m.x === m.cx
              ? <line x1={m.x} x2={m.x} y1={m.ly + lh} y2={m.ly + lh + 8} stroke={col} />
              : <line x1={m.x} x2={m.cx} y1={m.ly + lh} y2={Math.max(m.ly + lh, m.cy - 2)} stroke={col} strokeOpacity={0.45} />}
            <rect x={m.x - lw / 2} y={m.ly} width={lw} height={lh} rx={2} fill={sel ? col : 'rgb(var(--panel))'} stroke={col} />
            <text x={m.x} y={m.ly + lh * 0.72} textAnchor="middle" fontSize={fs} fontFamily="IBM Plex Mono" fill={sel ? 'rgb(var(--page))' : col}>{m.label}</text>
          </g>
        );
      })}
      {model.ticks.map((t, i) => (
        <text key={i} x={t.x} y={H + fs + 4} textAnchor={t.anchor} fontSize={fs} fill="rgb(var(--faint))" fontFamily="IBM Plex Mono">{t.label}</text>
      ))}
    </svg>
    </div>
  );
}
