// Diagramme de fiabilité : proba prédite (x) vs fréquence réelle (y).
// La diagonale = calibration parfaite. Reconstruit à partir de l'ECE global
// n'est pas possible ; ce composant prend des points explicites.

interface CalPoint {
  predicted: number; // %
  observed: number; // %
}

export function CalibrationChart({ points }: { points: CalPoint[] }) {
  const size = 320;
  const pad = 34;
  const scale = (v: number) => pad + (v / 100) * (size - 2 * pad);
  const y = (v: number) => size - pad - (v / 100) * (size - 2 * pad);

  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="w-full max-w-md" role="img" aria-label="Diagramme de fiabilité">
      {/* Grille */}
      {[0, 25, 50, 75, 100].map((g) => (
        <g key={g}>
          <line x1={scale(g)} y1={pad} x2={scale(g)} y2={size - pad} stroke="#1E293B" strokeWidth={1} />
          <line x1={pad} y1={y(g)} x2={size - pad} y2={y(g)} stroke="#1E293B" strokeWidth={1} />
          <text x={scale(g)} y={size - pad + 16} fill="#7C8AA0" fontSize={9} textAnchor="middle" fontFamily="monospace">
            {g}
          </text>
          <text x={pad - 8} y={y(g) + 3} fill="#7C8AA0" fontSize={9} textAnchor="end" fontFamily="monospace">
            {g}
          </text>
        </g>
      ))}

      {/* Diagonale = calibration parfaite */}
      <line
        x1={scale(0)} y1={y(0)} x2={scale(100)} y2={y(100)}
        stroke="#FFB020" strokeWidth={1.5} strokeDasharray="4 4" opacity={0.7}
      />

      {/* Ligne du modèle */}
      <polyline
        points={points.map((p) => `${scale(p.predicted)},${y(p.observed)}`).join(" ")}
        fill="none" stroke="#22C77E" strokeWidth={2}
      />
      {points.map((p, i) => (
        <circle key={i} cx={scale(p.predicted)} cy={y(p.observed)} r={3.5} fill="#22C77E" />
      ))}

      {/* Axes labels */}
      <text x={size / 2} y={size - 4} fill="#7C8AA0" fontSize={10} textAnchor="middle">
        Probabilité prédite (%)
      </text>
      <text x={12} y={size / 2} fill="#7C8AA0" fontSize={10} textAnchor="middle" transform={`rotate(-90 12 ${size / 2})`}>
        Fréquence réelle (%)
      </text>
    </svg>
  );
}
