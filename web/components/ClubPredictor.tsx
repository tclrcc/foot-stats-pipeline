"use client";

import { useState } from "react";
import type { Prediction, ClubTeam } from "@/lib/api";
import { TeamSelect, PredictionResult } from "./Predictor";

export function ClubPredictor({ league, teams }: { league: number; teams: ClubTeam[] }) {
  // Équipes de la saison en cours d'abord (déjà triées côté API)
  const names = teams.map((t) => t.team);
  const [home, setHome] = useState(names[0] ?? "");
  const [away, setAway] = useState(names[1] ?? "");
  const [loading, setLoading] = useState(false);
  const [pred, setPred] = useState<Prediction | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/clubs/predict?league=${league}&home=${encodeURIComponent(home)}&away=${encodeURIComponent(away)}`
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Erreur");
      setPred(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur inconnue");
      setPred(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="rounded-card border border-line bg-slate p-5">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-[1fr_auto_1fr]">
          <TeamSelect label="Domicile" value={home} onChange={setHome} options={names} accent="pitch" />
          <div className="flex items-end justify-center pb-2 font-mono text-sm text-mist">vs</div>
          <TeamSelect label="Extérieur" value={away} onChange={setAway} options={names} accent="clay" />
        </div>
        <div className="mt-4 flex items-center justify-between">
          <p className="text-xs text-mist">
            Avantage du terrain réel de la ligue appliqué au club à domicile.
          </p>
          <button
            onClick={run}
            disabled={loading || home === away}
            className="rounded-md bg-pitch px-5 py-2 text-sm font-semibold text-ink transition-opacity hover:opacity-90 disabled:opacity-40"
          >
            {loading ? "Calcul…" : "Prédire le match"}
          </button>
        </div>
        {home === away && (
          <p className="mt-2 text-xs text-signal">Choisis deux équipes différentes.</p>
        )}
      </div>

      {error && (
        <div className="rounded-card border border-clay/40 bg-clay/10 p-4 text-sm text-clay">
          {error}
        </div>
      )}

      {pred && <PredictionResult pred={pred} />}
    </div>
  );
}
