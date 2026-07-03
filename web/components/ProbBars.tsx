// Barre de probabilité segmentée façon tableau d'affichage.

interface Segment {
  label: string;
  value: number;
  color: string;
}

export function ProbBars({ segments }: { segments: Segment[] }) {
  return (
    <div>
      <div className="flex h-11 w-full overflow-hidden rounded-md border border-line">
        {segments.map((s) => (
          <div
            key={s.label}
            className="flex items-center justify-center text-xs font-semibold text-ink transition-all"
            style={{ width: `${s.value}%`, backgroundColor: s.color }}
            title={`${s.label} · ${s.value.toFixed(1)}%`}
          >
            {s.value >= 9 && <span className="tabular font-mono">{s.value.toFixed(0)}%</span>}
          </div>
        ))}
      </div>
      <div className="mt-2 flex justify-between text-xs">
        {segments.map((s) => (
          <div key={s.label} className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-sm" style={{ backgroundColor: s.color }} />
            <span className="text-mist">{s.label}</span>
            <span className="tabular font-mono text-chalk">{s.value.toFixed(1)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// Duel binaire (Over/Under, BTTS) : deux valeurs face à face.
export function DuoBar({
  leftLabel,
  leftValue,
  rightLabel,
  rightValue,
  leftColor = "#22C77E",
  rightColor = "#1E293B",
}: {
  leftLabel: string;
  leftValue: number;
  rightLabel: string;
  rightValue: number;
  leftColor?: string;
  rightColor?: string;
}) {
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs">
        <span className="text-chalk">
          {leftLabel} <span className="tabular font-mono text-mist">{leftValue.toFixed(1)}%</span>
        </span>
        <span className="text-chalk">
          <span className="tabular font-mono text-mist">{rightValue.toFixed(1)}%</span> {rightLabel}
        </span>
      </div>
      <div className="flex h-2 w-full overflow-hidden rounded-full">
        <div style={{ width: `${leftValue}%`, backgroundColor: leftColor }} />
        <div style={{ width: `${rightValue}%`, backgroundColor: rightColor }} />
      </div>
    </div>
  );
}
