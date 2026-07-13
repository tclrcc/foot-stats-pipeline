import Link from "next/link";
import { api, clubModel } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const [teams, perf, info, clubModels] = await Promise.all([
    api.teams(),
    api.modelPerformance().catch(() => null),
    api.modelInfo().catch(() => null),
    clubModel.models().catch(() => []),
  ]);
  const top = teams.slice(0, 6);
  const clubsTrained = clubModels.length > 0;

  return (
    <div>
      {/* Hero */}
      <section className="relative overflow-hidden rounded-card border border-line bg-slate">
        <div className="pitch-grid absolute inset-0" aria-hidden />
        <div className="relative px-6 py-12 sm:px-10 sm:py-16">
          <p className="mb-3 font-mono text-xs uppercase tracking-widest text-pitch">
            Modèle statistique · {info?.n_teams ?? "210"} équipes
          </p>
          <h1 className="max-w-2xl font-display text-4xl font-bold leading-[1.05] tracking-tight sm:text-5xl">
            Le football, lu à travers ses probabilités.
          </h1>
          <p className="mt-4 max-w-xl text-mist">
            Un moteur Dixon-Coles calibré estime les buts attendus, les résultats et
            la distribution des scores de n&apos;importe quelle affiche. Pas d&apos;intuition —
            des probabilités mesurées et vérifiées.
          </p>
          <div className="mt-7 flex flex-wrap gap-3">
            <Link
              href="/predict"
              className="rounded-md bg-pitch px-5 py-2.5 text-sm font-semibold text-ink transition-opacity hover:opacity-90"
            >
              Prédire un match
            </Link>
            <Link
              href="/model"
              className="rounded-md border border-line px-5 py-2.5 text-sm font-semibold text-chalk transition-colors hover:bg-ink"
            >
              Voir la précision du modèle
            </Link>
          </div>
        </div>
      </section>

      {/* Bandeau métriques */}
      {perf?.available && (
        <section className="mt-6 grid gap-4 sm:grid-cols-3">
          <Stat label="Précision (1N2)" value={`${perf.accuracy!.toFixed(1)}%`} sub="sur 788 matchs testés" />
          <Stat
            label="Gain vs modèle naïf"
            value={perf.gain_vs_baseline_pct != null ? `${perf.gain_vs_baseline_pct > 0 ? "+" : ""}${perf.gain_vs_baseline_pct.toFixed(1)}%` : "—"}
            sub="Brier score, walk-forward"
          />
          <Stat label="Erreur de calibration" value={`${perf.ece!.toFixed(2)}%`} sub="ECE — plus bas = mieux" />
        </section>
      )}

      {/* Passerelle vers le volet clubs */}
      <section className="mt-8 rounded-card border border-line bg-slate p-6 sm:p-7">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="mb-1.5 font-mono text-xs uppercase tracking-widest text-signal">
              Big 5 européen
            </p>
            <h2 className="font-display text-xl font-bold tracking-tight sm:text-2xl">
              Le même moteur, entraîné par championnat
            </h2>
            <p className="mt-1.5 max-w-xl text-sm text-mist">
              Ligue 1, Premier League, La Liga, Serie A, Bundesliga : classements,
              résultats, fiches joueurs et prédictions club, avec l&apos;avantage du
              terrain propre à chaque championnat.
              {clubsTrained && " Modèle validé par backtest sur chaque ligue."}
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap gap-3">
            <Link
              href="/clubs"
              className="rounded-md bg-signal px-5 py-2.5 text-sm font-semibold text-ink transition-opacity hover:opacity-90"
            >
              Explorer les championnats
            </Link>
            {clubsTrained && (
              <Link
                href="/clubs/predict"
                className="rounded-md border border-line px-5 py-2.5 text-sm font-semibold text-chalk transition-colors hover:bg-ink"
              >
                Prédire un match club
              </Link>
            )}
          </div>
        </div>
      </section>

      {/* Top équipes */}
      <section className="mt-10">
        <div className="mb-4 flex items-end justify-between">
          <h2 className="font-display text-xl font-bold tracking-tight">Top du classement</h2>
          <Link href="/teams" className="text-sm text-pitch hover:underline">
            Classement complet →
          </Link>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {top.map((t, i) => (
            <div key={t.team} className="rounded-card border border-line bg-slate p-4">
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs text-mist">#{i + 1}</span>
                <span className="font-mono text-lg font-bold tabular text-pitch">
                  {t.elo?.toFixed(0)}
                </span>
              </div>
              <div className="mt-1 font-display text-lg font-semibold">{t.team}</div>
              <div className="mt-2 flex gap-4 text-xs text-mist">
                <span>
                  att <span className="font-mono tabular text-chalk">{t.attack?.toFixed(2)}</span>
                </span>
                <span>
                  déf <span className="font-mono tabular text-chalk">{t.defense?.toFixed(2)}</span>
                </span>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="rounded-card border border-line bg-slate p-5">
      <div className="text-xs uppercase tracking-wider text-mist">{label}</div>
      <div className="mt-2 font-mono text-3xl font-bold tabular text-chalk">{value}</div>
      <div className="mt-1 text-xs text-mist">{sub}</div>
    </div>
  );
}
