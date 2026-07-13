import Link from "next/link";
import { clubDossier, ClubFormEntry, ClubStandingSnap } from "@/lib/api";
import { PredictionResult } from "@/components/Predictor";

export const dynamic = "force-dynamic";

function seasonLabel(s: number) {
  return `${s}-${String(s + 1).slice(-2)}`;
}

function fmtDate(d: string) {
  const dt = new Date(d.replace(" ", "T"));
  if (isNaN(dt.getTime())) return d;
  return dt.toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "numeric" });
}

export default async function ClubPreviewPage({
  searchParams,
}: {
  searchParams: { league?: string; home?: string; away?: string };
}) {
  const league = Number(searchParams.league);
  const home = searchParams.home ?? "";
  const away = searchParams.away ?? "";

  const d =
    league && home && away
      ? await clubDossier.get(league, home, away).catch(() => null)
      : null;

  if (!d) {
    return (
      <div>
        <Back />
        <div className="rounded-card border border-line bg-slate p-8 text-center text-mist">
          Dossier indisponible : équipe(s) inconnue(s) de cette ligue, ou paramètres manquants.
        </div>
      </div>
    );
  }

  return (
    <div>
      <Back />

      <header className="mb-8">
        <p className="mb-2 font-mono text-xs uppercase tracking-widest text-pitch">
          Avant-match · {d.league_name} · {seasonLabel(d.season)}
        </p>
        <h1 className="font-display text-3xl font-bold tracking-tight sm:text-4xl">
          <span className="text-pitch">{d.home_team}</span>
          <span className="mx-3 text-mist">vs</span>
          <span className="text-clay">{d.away_team}</span>
        </h1>
        {d.physionomie && (
          <p className="mt-2 text-mist">
            {d.physionomie.profile} · {d.physionomie.total_xg.toFixed(2)} buts attendus au total.
          </p>
        )}
      </header>

      {/* Prédiction complète */}
      {d.prediction ? (
        <PredictionResult pred={d.prediction} />
      ) : (
        <div className="rounded-card border border-line bg-slate p-6 text-center text-sm text-mist">
          Prédiction indisponible (équipe nouvelle pour le modèle — promue récemment).
        </div>
      )}

      {/* Classement + H2H */}
      <div className="mt-8 grid gap-8 lg:grid-cols-2">
        <section>
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-mist">
            Au classement ({seasonLabel(d.season)})
          </h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <StandingCard team={d.home_team} snap={d.standings.home} accent="pitch" />
            <StandingCard team={d.away_team} snap={d.standings.away} accent="clay" />
          </div>
        </section>

        <section>
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-mist">
            Confrontations directes
          </h2>
          <div className="rounded-card border border-line bg-slate p-4">
            {d.h2h.length === 0 ? (
              <p className="text-center text-sm text-mist">Aucune confrontation dans les données importées.</p>
            ) : (
              <>
                <p className="mb-3 text-sm text-mist">
                  Sur les {d.h2h.length} derniers :{" "}
                  <span className="text-pitch">{d.h2h_balance.home_wins} {d.home_team}</span>
                  {" · "}
                  <span className="text-royal">{d.h2h_balance.draws} nul{d.h2h_balance.draws > 1 ? "s" : ""}</span>
                  {" · "}
                  <span className="text-clay">{d.h2h_balance.away_wins} {d.away_team}</span>
                </p>
                <div className="space-y-1.5">
                  {d.h2h.map((m, i) => (
                    <div key={i} className="flex items-center gap-3 border-b border-line/30 py-1.5 text-sm">
                      <span className="w-24 shrink-0 font-mono text-xs tabular text-mist">{fmtDate(m.date)}</span>
                      <span className={`min-w-0 flex-1 truncate text-right ${m.home_score > m.away_score ? "font-medium text-chalk" : "text-mist"}`}>
                        {m.home_team}
                      </span>
                      <span className="shrink-0 rounded bg-ink px-2 py-0.5 font-mono text-xs tabular text-chalk">
                        {m.home_score}–{m.away_score}
                      </span>
                      <span className={`min-w-0 flex-1 truncate ${m.away_score > m.home_score ? "font-medium text-chalk" : "text-mist"}`}>
                        {m.away_team}
                      </span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </section>
      </div>

      {/* Forme récente */}
      <section className="mt-8">
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-mist">
          Forme récente (5 derniers matchs de championnat)
        </h2>
        <div className="grid gap-5 sm:grid-cols-2">
          <FormColumn team={d.home_team} entries={d.form.home} accent="pitch" />
          <FormColumn team={d.away_team} entries={d.form.away} accent="clay" />
        </div>
      </section>

      <p className="mt-8 text-xs text-mist">
        Compositions officielles et indisponibilités : à venir sur ce dossier — les commandes de
        synchronisation sont prêtes, le branchement club arrive.
      </p>
    </div>
  );
}

function StandingCard({ team, snap, accent }: { team: string; snap: ClubStandingSnap | null; accent: "pitch" | "clay" }) {
  return (
    <div className="rounded-card border border-line bg-slate p-4">
      <div className={`mb-2 truncate font-display text-lg font-semibold text-${accent}`}>{team}</div>
      {!snap ? (
        <p className="text-sm text-mist">Pas encore classé cette saison.</p>
      ) : (
        <div className="flex items-baseline gap-4">
          <span className="font-mono text-3xl font-bold tabular text-chalk">#{snap.rank}</span>
          <div className="text-xs text-mist">
            <div><span className="font-mono tabular text-chalk">{snap.points}</span> pts en {snap.played} MJ</div>
            <div>diff <span className={`font-mono tabular ${snap.gd > 0 ? "text-pitch" : snap.gd < 0 ? "text-clay" : "text-chalk"}`}>{snap.gd > 0 ? `+${snap.gd}` : snap.gd}</span></div>
          </div>
          <span className="ml-auto flex gap-1">
            {snap.form.map((f, i) => (
              <span key={i} className={`grid h-4 w-4 place-items-center rounded-sm text-[10px] font-bold text-ink ${f === "V" ? "bg-pitch" : f === "N" ? "bg-royal" : "bg-clay"}`}>
                {f}
              </span>
            ))}
          </span>
        </div>
      )}
    </div>
  );
}

function FormColumn({ team, entries, accent }: { team: string; entries: ClubFormEntry[]; accent: "pitch" | "clay" }) {
  return (
    <div className="rounded-card border border-line bg-slate p-4">
      <div className={`mb-2 truncate font-display text-lg font-semibold text-${accent}`}>{team}</div>
      <div className="space-y-1.5">
        {entries.map((e, i) => (
          <div key={i} className="flex items-center gap-3 border-b border-line/30 py-1 text-sm">
            <span className={`grid h-5 w-5 shrink-0 place-items-center rounded text-[11px] font-bold text-ink ${e.result === "V" ? "bg-pitch" : e.result === "N" ? "bg-royal" : "bg-clay"}`}>
              {e.result}
            </span>
            <span className="w-14 shrink-0 font-mono text-xs tabular text-mist">{e.score}</span>
            <span className="min-w-0 flex-1 truncate text-chalk">
              {e.venue === "home" ? "vs" : "à"} {e.opponent}
            </span>
            <span className="shrink-0 font-mono text-[11px] tabular text-mist">{fmtDate(e.date)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Back() {
  return (
    <Link href="/clubs" className="mb-5 inline-block text-sm text-pitch hover:underline">
      ← Championnats
    </Link>
  );
}
