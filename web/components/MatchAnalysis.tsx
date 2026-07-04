"use client";

import { useState, useEffect } from "react";
import type { MatchDossier, MatchDynamics, TeamRating, TeamFormData, HeadToHead, StrengthSide, KeyPlayer, CoachInfo } from "@/lib/api";
import { ProbBars, DuoBar } from "./ProbBars";
import { ScoreHeatmap } from "./ScoreHeatmap";

export function MatchAnalysis({
  teams,
  initialHome,
  initialAway,
  autoRun = false,
}: {
  teams: TeamRating[];
  initialHome?: string;
  initialAway?: string;
  autoRun?: boolean;
}) {
  const names = teams.map((t) => t.team);
  const [home, setHome] = useState(initialHome && names.includes(initialHome) ? initialHome : "Spain");
  const [away, setAway] = useState(initialAway && names.includes(initialAway) ? initialAway : "Portugal");
  const [loading, setLoading] = useState(false);
  const [dossier, setDossier] = useState<MatchDossier | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(h = home, a = away) {
    setLoading(true);
    setError(null);
    try {
      const today = new Date().toISOString().slice(0, 10);
      const res = await fetch(
        `/api/dossier?home=${encodeURIComponent(h)}&away=${encodeURIComponent(a)}&neutral=true&date=${today}`
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Erreur");
      setDossier(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur inconnue");
      setDossier(null);
    } finally {
      setLoading(false);
    }
  }

  // Auto-charge le dossier si on arrive avec ?home=&away=
  useEffect(() => {
    if (autoRun && initialHome && initialAway) run(initialHome, initialAway);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-6">
      <div className="rounded-card border border-line bg-slate p-5">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-[1fr_auto_1fr]">
          <Select label="Domicile" value={home} onChange={setHome} options={names} accent="pitch" />
          <div className="flex items-end justify-center pb-2 font-mono text-sm text-mist">vs</div>
          <Select label="Extérieur" value={away} onChange={setAway} options={names} accent="clay" />
        </div>
        <div className="mt-4 flex justify-end">
          <button
            onClick={() => run()}
            disabled={loading || home === away}
            className="rounded-md bg-pitch px-5 py-2 text-sm font-semibold text-ink transition-opacity hover:opacity-90 disabled:opacity-40"
          >
            {loading ? "Analyse…" : "Générer le dossier"}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-card border border-clay/40 bg-clay/10 p-4 text-sm text-clay">{error}</div>
      )}

      {dossier && <Dossier d={dossier} />}
    </div>
  );
}

function Dossier({ d }: { d: MatchDossier }) {
  const f = d.fixture;
  return (
    <div className="space-y-6">
      {/* En-tête */}
      <div className="rounded-card border border-line bg-slate p-5">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <Tag>{f.stage}</Tag>
          {f.host_playing && <Tag accent="signal">Pays hôte : {f.host_playing}</Tag>}
          {f.neutral && <Tag>Terrain neutre</Tag>}
        </div>
        <div className="mt-4 flex items-center justify-center gap-6">
          <TeamName name={f.home_team} rank={d.strength.home.elo_rank} color="text-pitch" />
          <span className="font-mono text-sm text-mist">vs</span>
          <TeamName name={f.away_team} rank={d.strength.away.elo_rank} color="text-clay" />
        </div>
      </div>

      {/* À la une : angles narratifs */}
      <Panel title="À la une">
        <ul className="space-y-2">
          {d.storylines.map((s, i) => (
            <li key={i} className="flex gap-2.5 text-sm text-chalk">
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-signal" />
              <span>{s}</span>
            </li>
          ))}
        </ul>
      </Panel>

      {/* Physionomie & lecture tactique */}
      {d.dynamics && <DynamicsPanel dyn={d.dynamics} homeName={f.home_team} awayName={f.away_team} />}

      {/* Sur les bancs : sélectionneurs */}
      {d.coaches && (d.coaches.home || d.coaches.away) && (
        <Panel title="Sur les bancs">
          <div className="grid gap-5 sm:grid-cols-2">
            <CoachCard coach={d.coaches.home} team={f.home_team} accent="pitch" />
            <CoachCard coach={d.coaches.away} team={f.away_team} accent="clay" />
          </div>
        </Panel>
      )}

      {/* Comparaison des forces */}
      <Panel title="Rapport de force">
        <StrengthCompare home={d.strength.home} away={d.strength.away} homeName={f.home_team} awayName={f.away_team} />
      </Panel>

      {/* Formes */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title={`Forme — ${f.home_team}`}>
          <FormStrip form={d.form.home} />
        </Panel>
        <Panel title={`Forme — ${f.away_team}`}>
          <FormStrip form={d.form.away} />
        </Panel>
      </div>

      {/* Face-à-face */}
      <Panel title="Face-à-face">
        <H2HPanel h2h={d.head_to_head} homeName={f.home_team} awayName={f.away_team} />
      </Panel>

      {/* Hommes clés */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title={`Hommes clés — ${f.home_team}`}>
          <Players players={d.key_players.home} />
        </Panel>
        <Panel title={`Hommes clés — ${f.away_team}`}>
          <Players players={d.key_players.away} />
        </Panel>
      </div>

      {/* Prédiction */}
      <div className="rounded-card border border-line bg-slate p-5">
        <h3 className="mb-4 text-xs font-semibold uppercase tracking-wider text-mist">Prédiction du modèle</h3>
        <div className="mb-5 flex items-center justify-center gap-6">
          <Xg name={f.home_team} xg={d.prediction.xg_home} color="text-pitch" />
          <span className="font-mono text-xs text-mist">buts attendus</span>
          <Xg name={f.away_team} xg={d.prediction.xg_away} color="text-clay" />
        </div>
        <ProbBars
          segments={[
            { label: f.home_team, value: d.prediction.markets.home_win, color: "#22C77E" },
            { label: "Nul", value: d.prediction.markets.draw, color: "#3B82F6" },
            { label: f.away_team, value: d.prediction.markets.away_win, color: "#FF5A6A" },
          ]}
        />
        <div className="mt-5 grid gap-5 sm:grid-cols-2">
          <DuoBar leftLabel="+2.5 buts" leftValue={d.prediction.markets.over_2_5} rightLabel="-2.5" rightValue={d.prediction.markets.under_2_5} />
          <DuoBar leftLabel="Les deux marquent" leftValue={d.prediction.markets.btts_yes} rightLabel="Non" rightValue={d.prediction.markets.btts_no} leftColor="#FFB020" />
        </div>
        <div className="mt-6">
          <ScoreHeatmap scorelines={d.prediction.top_scorelines} homeTeam={f.home_team} awayTeam={f.away_team} />
        </div>
      </div>
    </div>
  );
}

// ─── Sous-composants ───

function CoachCard({ coach, team, accent }: { coach: CoachInfo | null; team: string; accent: "pitch" | "clay" }) {
  if (!coach) {
    return (
      <div className="rounded-md border border-line bg-ink/40 p-4 text-sm text-mist">
        {team} — sélectionneur non renseigné.
      </div>
    );
  }
  return (
    <div className="rounded-md border border-line bg-ink/40 p-4">
      <div className="flex items-baseline justify-between">
        <span className={`font-display text-lg font-semibold text-${accent}`}>{coach.name}</span>
        {coach.formation && <span className="font-mono text-xs text-mist">{coach.formation}</span>}
      </div>
      <div className="mt-0.5 text-xs text-mist">
        {team}{coach.since ? ` · depuis ${coach.since}` : ""}
      </div>
      {coach.style && coach.style.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {coach.style.map((s) => (
            <span key={s} className="rounded border border-line px-2 py-0.5 text-xs text-chalk">{s}</span>
          ))}
        </div>
      )}
      {coach.note && <p className="mt-3 text-sm leading-relaxed text-mist">{coach.note}</p>}
    </div>
  );
}

function DynamicsPanel({ dyn, homeName, awayName }: { dyn: MatchDynamics; homeName: string; awayName: string }) {
  const sc = dyn.scenarios;
  const rows: { label: string; value: number }[] = [
    { label: "Match serré (≤ 1 but d'écart)", value: sc.tight },
    { label: "Écart net (2 buts ou +)", value: sc.blowout },
    { label: `Cage inviolée — ${homeName}`, value: sc.clean_sheet_home },
    { label: `Cage inviolée — ${awayName}`, value: sc.clean_sheet_away },
    { label: "Moins de 1,5 but", value: sc.under_1_5 },
    { label: "Plus de 3,5 buts", value: sc.over_3_5 },
  ];
  if (sc.extra_time !== null) rows.push({ label: "Nul à 90' → prolongation probable", value: sc.extra_time });

  return (
    <div className="rounded-card border border-line bg-slate p-5">
      <h3 className="mb-4 text-xs font-semibold uppercase tracking-wider text-mist">
        Physionomie de la rencontre
      </h3>

      {/* Profil + jauge de tempo */}
      <div className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="font-display text-2xl font-bold text-chalk">{dyn.profile}</div>
          <div className="mt-1 text-xs text-mist">{dyn.total_xg} buts attendus au total</div>
        </div>
        <div className="w-full sm:w-56">
          <div className="mb-1 flex justify-between text-xs text-mist">
            <span>Verrouillé</span><span>Ouvert</span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-line">
            <div className="h-full rounded-full bg-gradient-to-r from-royal to-signal" style={{ width: `${Math.max(4, dyn.tempo)}%` }} />
          </div>
          <div className="mt-1 text-right font-mono text-xs tabular text-mist">tempo {dyn.tempo}/100</div>
        </div>
      </div>

      {/* Scénarios probables */}
      <div className="grid gap-x-6 gap-y-2.5 sm:grid-cols-2">
        {rows.map((r) => (
          <div key={r.label}>
            <div className="mb-1 flex justify-between text-xs">
              <span className="text-mist">{r.label}</span>
              <span className="font-mono tabular text-chalk">{r.value.toFixed(0)}%</span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-line">
              <div className="h-full rounded-full bg-pitch" style={{ width: `${r.value}%` }} />
            </div>
          </div>
        ))}
      </div>

      {/* Lecture tactique */}
      {dyn.tactical_read.length > 0 && (
        <div className="mt-5 border-t border-line pt-4">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-mist">Lecture tactique</div>
          <ul className="space-y-2">
            {dyn.tactical_read.map((r, i) => (
              <li key={i} className="flex gap-2.5 text-sm text-chalk">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-pitch" />
                <span>{r}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function StrengthCompare({ home, away, homeName, awayName }: { home: StrengthSide; away: StrengthSide; homeName: string; awayName: string }) {
  const rows = [
    { label: "ELO", h: home.elo ?? 0, a: away.elo ?? 0, fmt: (v: number) => v.toFixed(0), higher: true },
    { label: "Attaque", h: home.attack ?? 0, a: away.attack ?? 0, fmt: (v: number) => v.toFixed(2), higher: true },
    { label: "Défense", h: home.defense ?? 0, a: away.defense ?? 0, fmt: (v: number) => v.toFixed(2), higher: false },
  ];
  return (
    <div className="space-y-3">
      <div className="flex justify-between text-xs">
        <span className="font-semibold text-pitch">{homeName}</span>
        <span className="font-semibold text-clay">{awayName}</span>
      </div>
      {rows.map((r) => {
        const total = r.h + r.a || 1;
        const hPct = (r.h / total) * 100;
        // "higher is better" détermine qui est mis en avant
        const hBetter = r.higher ? r.h >= r.a : r.h <= r.a;
        return (
          <div key={r.label}>
            <div className="mb-1 flex justify-between font-mono text-xs tabular">
              <span className={hBetter ? "text-pitch" : "text-mist"}>{r.fmt(r.h)}</span>
              <span className="text-mist">{r.label}</span>
              <span className={!hBetter ? "text-clay" : "text-mist"}>{r.fmt(r.a)}</span>
            </div>
            <div className="flex h-1.5 overflow-hidden rounded-full bg-line">
              <div style={{ width: `${hPct}%`, backgroundColor: "#22C77E" }} />
              <div style={{ width: `${100 - hPct}%`, backgroundColor: "#FF5A6A" }} />
            </div>
          </div>
        );
      })}
      <p className="pt-1 text-xs text-mist">Défense : valeur plus basse = meilleure. Barres normalisées entre les deux équipes.</p>
    </div>
  );
}

function FormStrip({ form }: { form: TeamFormData }) {
  const s = form.summary;
  const color = (r: string) => (r === "V" ? "bg-pitch text-ink" : r === "N" ? "bg-royal text-ink" : "bg-clay text-ink");
  return (
    <div>
      <div className="mb-3 flex gap-1.5">
        {form.matches.slice().reverse().map((m, i) => (
          <span key={i} className={`grid h-7 w-7 place-items-center rounded font-mono text-xs font-bold ${color(m.result)}`} title={`${m.opponent} ${m.score} (${m.competition})`}>
            {m.result}
          </span>
        ))}
      </div>
      <div className="mb-3 flex gap-4 text-xs text-mist">
        <span><span className="font-mono tabular text-chalk">{s.w}</span>V</span>
        <span><span className="font-mono tabular text-chalk">{s.d}</span>N</span>
        <span><span className="font-mono tabular text-chalk">{s.l}</span>D</span>
        <span>Buts <span className="font-mono tabular text-chalk">{s.gf}:{s.ga}</span></span>
      </div>
      <div className="space-y-1">
        {form.matches.map((m, i) => (
          <div key={i} className="flex items-center justify-between border-b border-line/40 py-1 text-xs">
            <span className="text-mist">{m.date}</span>
            <span className="text-chalk">{m.venue === "dom" ? "vs" : "@"} {m.opponent}</span>
            <span className={`font-mono tabular font-semibold ${m.result === "V" ? "text-pitch" : m.result === "D" ? "text-clay" : "text-mist"}`}>{m.score}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function H2HPanel({ h2h, homeName, awayName }: { h2h: HeadToHead; homeName: string; awayName: string }) {
  if (h2h.played === 0) {
    return <p className="text-sm text-mist">Première confrontation de l&apos;histoire entre ces deux équipes.</p>;
  }
  const total = h2h.home_wins + h2h.draws + h2h.away_wins || 1;
  return (
    <div>
      <div className="mb-2 flex justify-between text-xs">
        <span className="text-pitch">{h2h.home_wins} V {homeName}</span>
        <span className="text-mist">{h2h.draws} nuls</span>
        <span className="text-clay">{h2h.away_wins} V {awayName}</span>
      </div>
      <div className="flex h-2.5 overflow-hidden rounded-full">
        <div style={{ width: `${(h2h.home_wins / total) * 100}%`, backgroundColor: "#22C77E" }} />
        <div style={{ width: `${(h2h.draws / total) * 100}%`, backgroundColor: "#1E293B" }} />
        <div style={{ width: `${(h2h.away_wins / total) * 100}%`, backgroundColor: "#FF5A6A" }} />
      </div>
      <div className="mt-2 text-center text-xs text-mist">
        {h2h.played} confrontations · buts cumulés {h2h.home_goals}:{h2h.away_goals}
      </div>
      <div className="mt-4 space-y-1">
        {h2h.recent.map((m, i) => (
          <div key={i} className="flex items-center justify-between border-b border-line/40 py-1 text-xs">
            <span className="text-mist">{m.date.slice(0, 4)}</span>
            <span className="text-chalk">{m.home} <span className="font-mono tabular text-mist">{m.score}</span> {m.away}</span>
            <span className="text-mist">{m.competition}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Players({ players }: { players: KeyPlayer[] }) {
  if (!players.length) return <p className="text-sm text-mist">Données joueurs indisponibles.</p>;
  const max = Math.max(...players.map((p) => p.dependency_pct));
  return (
    <div className="space-y-2">
      {players.slice(0, 5).map((p) => (
        <div key={p.name} className="flex items-center gap-3">
          <span className="w-36 truncate text-sm text-chalk">{p.name}</span>
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-line">
            <div className="h-full rounded-full bg-signal" style={{ width: `${(p.dependency_pct / max) * 100}%` }} />
          </div>
          <span className="w-16 text-right font-mono text-xs tabular text-mist">{p.goals}b · {p.dependency_pct.toFixed(0)}%</span>
        </div>
      ))}
      <p className="pt-1 text-xs text-mist">Buts sur 5 ans · part dans les buts de l&apos;équipe.</p>
    </div>
  );
}

// ─── Primitives ───
function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-card border border-line bg-slate p-5">
      <h3 className="mb-4 text-xs font-semibold uppercase tracking-wider text-mist">{title}</h3>
      {children}
    </div>
  );
}
function Tag({ children, accent }: { children: React.ReactNode; accent?: "signal" }) {
  return (
    <span className={`rounded border px-2 py-0.5 ${accent === "signal" ? "border-signal/40 text-signal" : "border-line text-mist"}`}>
      {children}
    </span>
  );
}
function TeamName({ name, rank, color }: { name: string; rank: number | null; color: string }) {
  return (
    <div className="text-center">
      <div className={`font-display text-xl font-bold ${color}`}>{name}</div>
      {rank && <div className="mt-0.5 font-mono text-xs text-mist">#{rank} ELO</div>}
    </div>
  );
}
function Xg({ name, xg, color }: { name: string; xg: number; color: string }) {
  return (
    <div className="text-center">
      <div className={`font-mono text-3xl font-bold tabular ${color}`}>{xg.toFixed(2)}</div>
      <div className="mt-1 max-w-[9rem] text-xs text-mist">{name}</div>
    </div>
  );
}
function Select({ label, value, onChange, options, accent }: { label: string; value: string; onChange: (v: string) => void; options: string[]; accent: "pitch" | "clay" }) {
  return (
    <label className="block">
      <span className={`mb-1.5 block text-xs uppercase tracking-wider text-${accent}`}>{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)} className="w-full rounded-md border border-line bg-ink px-3 py-2.5 font-display text-lg text-chalk outline-none focus:border-mist">
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </label>
  );
}
