import Link from "next/link";
import { clubModel } from "@/lib/api";
import { ClubPredictor } from "@/components/ClubPredictor";

export const dynamic = "force-dynamic";

function seasonLabel(s: number) {
  return `${s}-${String(s + 1).slice(-2)}`;
}

export default async function ClubPredictPage({
  searchParams,
}: {
  searchParams: { league?: string };
}) {
  const models = await clubModel.models().catch(() => []);

  if (models.length === 0) {
    return (
      <div>
        <Header />
        <div className="rounded-card border border-line bg-slate p-8 text-center text-mist">
          Aucun championnat entraîné. Lance{" "}
          <code className="font-mono text-chalk">
            python src/models/club_dixon_coles.py train --league big5
          </code>{" "}
          sur le serveur.
        </div>
      </div>
    );
  }

  const leagueId = Number(searchParams.league) || models[0].league_id;
  const current = models.find((m) => m.league_id === leagueId) ?? models[0];
  const teams = await clubModel.teams(current.league_id).catch(() => []);
  const bt = current.backtest;

  return (
    <div>
      <Header />

      {/* Sélecteur de championnat entraîné */}
      <div className="mb-8 flex flex-wrap gap-2">
        {models.map((m) => (
          <Link
            key={m.league_id}
            href={`/clubs/predict?league=${m.league_id}`}
            className={`rounded-md border px-3 py-1.5 text-sm transition-colors ${
              m.league_id === current.league_id
                ? "border-pitch bg-pitch/10 text-pitch"
                : "border-line text-mist hover:border-mist"
            }`}
          >
            {m.league_name}
          </Link>
        ))}
      </div>

      <ClubPredictor league={current.league_id} teams={teams} />

      {/* Carte d'identité du modèle de la ligue */}
      <div className="mt-10 rounded-card border border-line bg-slate p-5">
        <h2 className="mb-4 text-xs font-semibold uppercase tracking-wider text-mist">
          Le modèle {current.league_name}
        </h2>
        <div className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3 lg:grid-cols-6">
          <Metric v={String(current.n_matches)} l="Matchs d'entraînement" />
          <Metric v={current.gamma.toFixed(3)} l="γ — avantage du terrain" />
          <Metric v={current.rho.toFixed(3)} l="ρ — corrélation petits scores" />
          {bt && (
            <>
              <Metric v={`${(bt.accuracy * 100).toFixed(1)}%`} l={`Précision 1N2 (${bt.n_matches} matchs ${seasonLabel(bt.test_season)})`} />
              <Metric v={`${bt.gain_vs_baseline_pct > 0 ? "+" : ""}${bt.gain_vs_baseline_pct.toFixed(1)}%`} l="Gain Brier vs naïf (walk-forward)" />
              {bt.ece != null && <Metric v={`${(bt.ece * 100).toFixed(2)}%`} l="Erreur de calibration (ECE)" />}
            </>
          )}
        </div>
        <p className="mt-4 text-xs text-mist">
          Modèle Dixon-Coles estimé par maximum de vraisemblance sur les saisons importées
          (pondération décroissante dans le temps), avantage du terrain propre au championnat.
          Entraîné le {current.trained_at?.slice(0, 10)}.
          {!bt && " Backtest non encore lancé pour cette ligue."}
        </p>
      </div>
    </div>
  );
}

function Metric({ v, l }: { v: string; l: string }) {
  return (
    <div>
      <div className="font-mono text-xl font-bold tabular text-chalk">{v}</div>
      <div className="mt-0.5 text-xs text-mist">{l}</div>
    </div>
  );
}

function Header() {
  return (
    <header className="mb-8">
      <p className="mb-2 font-mono text-xs uppercase tracking-widest text-pitch">Club</p>
      <h1 className="font-display text-3xl font-bold tracking-tight sm:text-4xl">
        Prédire un match de championnat
      </h1>
      <p className="mt-2 max-w-2xl text-mist">
        Probabilités 1N2, buts attendus et distribution des scores, estimés par un modèle
        entraîné championnat par championnat — avec l&apos;avantage du terrain réel.
      </p>
    </header>
  );
}
