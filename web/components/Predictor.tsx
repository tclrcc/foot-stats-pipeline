"use client";

import { useState } from "react";
import type { Prediction, TeamRating } from "@/lib/api";
import { ProbBars, DuoBar } from "./ProbBars";
import { ScoreHeatmap } from "./ScoreHeatmap";

export function Predictor({ teams }: { teams: TeamRating[] }) {
  const names = teams.map((t) => t.team);
  const [home, setHome] = useState("France");
  const [away, setAway] = useState("Brazil");
  const [neutral, setNeutral] = useState(true);
  const [loading, setLoading] = useState(false);
  const [pred, setPred] = useState<Prediction | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/predict?home=${encodeURIComponent(home)}&away=${encodeURIComponent(
          away
        )}&neutral=${neutral}`
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
      {/* Sélecteurs */}
      <div className="rounded-card border border-line bg-slate p-5">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-[1fr_auto_1fr]">
          <TeamSelect label="Domicile" value={home} onChange={setHome} options={names} accent="pitch" />
          <div className="flex items-end justify-center pb-2 font-mono text-sm text-mist">
            vs
          </div>
          <TeamSelect label="Extérieur" value={away} onChange={setAway} options={names} accent="clay" />
        </div>
        <div className="mt-4 flex items-center justify-between">
          <label className="flex cursor-pointer items-center gap-2 text-sm text-mist">
            <input
              type="checkbox"
              checked={neutral}
              onChange={(e) => setNeutral(e.target.checked)}
              className="h-4 w-4 accent-pitch"
            />
            Terrain neutre
          </label>
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

function TeamSelect({
  label,
  value,
  onChange,
  options,
  accent,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: string[];
  accent: "pitch" | "clay";
}) {
  return (
    <label className="block">
      <span className={`mb-1.5 block text-xs uppercase tracking-wider text-${accent}`}>
        {label}
      </span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-md border border-line bg-ink px-3 py-2.5 font-display text-lg text-chalk outline-none focus:border-mist"
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </label>
  );
}

function PredictionResult({ pred }: { pred: Prediction }) {
  const m = pred.markets;
  return (
    <div className="space-y-6">
      {/* xG scoreboard */}
      <div className="rounded-card border border-line bg-slate p-5">
        <div className="flex items-center justify-center gap-6">
          <TeamXg name={pred.home_team} xg={pred.xg_home} color="text-pitch" />
          <span className="font-mono text-sm text-mist">buts attendus</span>
          <TeamXg name={pred.away_team} xg={pred.xg_away} color="text-clay" />
        </div>
      </div>

      {/* 1N2 */}
      <Panel title="Résultat (1N2)">
        <ProbBars
          segments={[
            { label: pred.home_team, value: m.home_win, color: "#22C77E" },
            { label: "Nul", value: m.draw, color: "#3B82F6" },
            { label: pred.away_team, value: m.away_win, color: "#FF5A6A" },
          ]}
        />
      </Panel>

      <div className="grid gap-6 sm:grid-cols-2">
        <Panel title="Total de buts">
          <div className="space-y-3">
            <DuoBar leftLabel="+2.5" leftValue={m.over_2_5} rightLabel="-2.5" rightValue={m.under_2_5} />
            <DuoBar leftLabel="+1.5" leftValue={m.over_1_5} rightLabel="-1.5" rightValue={100 - m.over_1_5} />
          </div>
        </Panel>
        <Panel title="Les deux équipes marquent">
          <DuoBar
            leftLabel="Oui"
            leftValue={m.btts_yes}
            rightLabel="Non"
            rightValue={m.btts_no}
            leftColor="#FFB020"
          />
        </Panel>
      </div>

      {/* Heatmap signature */}
      <Panel title="Scores les plus probables">
        <ScoreHeatmap
          scorelines={pred.top_scorelines}
          homeTeam={pred.home_team}
          awayTeam={pred.away_team}
        />
      </Panel>
    </div>
  );
}

function TeamXg({ name, xg, color }: { name: string; xg: number; color: string }) {
  return (
    <div className="text-center">
      <div className={`font-mono text-4xl font-bold tabular ${color}`}>{xg.toFixed(2)}</div>
      <div className="mt-1 max-w-[10rem] text-sm text-mist">{name}</div>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-card border border-line bg-slate p-5">
      <h3 className="mb-4 text-xs font-semibold uppercase tracking-wider text-mist">{title}</h3>
      {children}
    </div>
  );
}
