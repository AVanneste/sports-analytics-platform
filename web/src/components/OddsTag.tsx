import React from 'react';

const fmt = (v?: number | null) => (typeof v === 'number' && isFinite(v) ? v.toFixed(2) : '-');

/** Fair (model) and bookmaker odds, each labelled so the two never read as the same number. */
export const OddsTag: React.FC<{ fair?: number | null; book?: number | null }> = ({ fair, book }) => (
  <span className="flex items-center gap-2 font-mono text-[11px] shrink-0">
    <span title="Model fair odds">
      <span className="text-[9px] uppercase tracking-wider text-slate-500">Fair</span>{' '}
      <span className="text-emerald-400 font-bold">{fmt(fair)}</span>
    </span>
    <span title="Bookmaker odds" className="rounded bg-dark-800 px-1.5 py-0.5">
      <span className="text-[9px] uppercase tracking-wider text-slate-500">Book</span>{' '}
      <span className="text-white font-bold">{fmt(book)}</span>
    </span>
  </span>
);
