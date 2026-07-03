// Élément signature : heatmap des scores exacts probables.
// Chaque cellule (i,j) = probabilité du score i-j, colorée par intensité.

interface ScoreLine {
  score: string;
  probability: number;
}

const MAX = 5; // affiche les scores de 0 à 5 buts par équipe

export function ScoreHeatmap({
  scorelines,
  homeTeam,
  awayTeam,
}: {
  scorelines: ScoreLine[];
  homeTeam: string;
  awayTeam: string;
}) {
  // Reconstruit une matrice (home x away) depuis la liste top scores.
  const grid: Record<string, number> = {};
  let peak = 0;
  for (const s of scorelines) {
    grid[s.score] = s.probability;
    if (s.probability > peak) peak = s.probability;
  }
  const topScore = scorelines[0]?.score;

  const cellColor = (p: number | undefined) => {
    if (!p || p <= 0) return "transparent";
    const t = Math.min(1, p / (peak || 1));
    // Interpolation ink → pitch
    const a = 0.08 + t * 0.85;
    return `rgba(34, 199, 126, ${a.toFixed(3)})`;
  };

  return (
    <div className="overflow-x-auto">
      <div className="inline-block">
        <div className="mb-2 text-center text-xs uppercase tracking-wider text-mist">
          {awayTeam} →
        </div>
        <div className="flex">
          <div
            className="flex items-center justify-center pr-2 text-xs uppercase tracking-wider text-mist"
            style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}
          >
            {homeTeam} →
          </div>
          <div>
            {/* En-tête colonnes (buts extérieur) */}
            <div className="flex">
              <div className="h-7 w-7" />
              {Array.from({ length: MAX + 1 }).map((_, j) => (
                <div
                  key={j}
                  className="grid h-7 w-11 place-items-center font-mono text-xs text-mist"
                >
                  {j}
                </div>
              ))}
            </div>
            {/* Lignes (buts domicile) */}
            {Array.from({ length: MAX + 1 }).map((_, i) => (
              <div key={i} className="flex">
                <div className="grid h-11 w-7 place-items-center font-mono text-xs text-mist">
                  {i}
                </div>
                {Array.from({ length: MAX + 1 }).map((_, j) => {
                  const key = `${i}-${j}`;
                  const p = grid[key];
                  const isTop = key === topScore;
                  return (
                    <div
                      key={j}
                      className={`grid h-11 w-11 place-items-center border ${
                        isTop ? "border-signal" : "border-line/60"
                      }`}
                      style={{ backgroundColor: cellColor(p) }}
                      title={`${key} · ${p ? p.toFixed(1) : "0"}%`}
                    >
                      {p !== undefined && p >= 2 && (
                        <span
                          className={`tabular font-mono text-[11px] ${
                            (p / (peak || 1)) > 0.55 ? "text-ink" : "text-chalk"
                          }`}
                        >
                          {p.toFixed(0)}
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
        <div className="mt-3 flex items-center justify-center gap-2 text-xs text-mist">
          <span>Moins probable</span>
          <div className="flex">
            {[0.1, 0.3, 0.5, 0.7, 0.9].map((t) => (
              <span
                key={t}
                className="h-3 w-6"
                style={{ backgroundColor: `rgba(34,199,126,${t})` }}
              />
            ))}
          </div>
          <span>Plus probable</span>
          <span className="ml-3 flex items-center gap-1">
            <span className="h-3 w-3 border border-signal" /> score le plus probable
          </span>
        </div>
      </div>
    </div>
  );
}
