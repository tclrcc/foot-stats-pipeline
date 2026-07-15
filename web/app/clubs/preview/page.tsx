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

      {/* À la une */}
      {d.storylines.length > 0 && (
        <div className="mb-8 rounded-card border border-line bg-slate p-5">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-mist">
            À la une
          </h2>
          <ul className="space-y-2">
            {d.storylines.map((line, i) => (
              <li key={i} className="flex gap-2.5 text-sm text-chalk">
                <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-signal" />
                <span>{line}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Prédiction complète */}
      {d.prediction ? (
        <PredictionResult pred={d.prediction} />
      ) : (
        <div className="rounded-card border border-line bg-slate p-6 text-center text-sm text-mist">
          Prédiction indisponible (équipe nouvelle pour le modèle — promue récemment).
        </div>
      )}

      {/* Compositions officielles */}
      {d.lineups && (
        <div className="mt-8 rounded-card border border-line bg-slate p-5">
          <h2 className="mb-4 text-xs font-semibold uppercase tracking-wider text-mist">
            Compositions officielles
          </h2>
          <div className="grid gap-5 sm:grid-cols-2">
            {(["home", "away"] as const).map((side) => {
              const lu = d.lineups![side];
              const accent = side === "home" ? "pitch" : "clay";
              return (
                <div key={side} className="rounded-md border border-line bg-ink/40 p-4">
                  <div className="mb-3 flex items-baseline justify-between">
                    <span className={`font-display text-lg font-semibold text-${accent}`}>{lu.team}</span>
                    {lu.formation && (
                      <span className="rounded border border-line px-2 py-0.5 font-mono text-xs text-chalk">{lu.formation}</span>
                    )}
                  </div>
                  <div className="space-y-1">
                    {lu.xi.map((p, i) => (
                      <div key={i} className="flex items-center gap-2 border-b border-line/30 py-1 text-sm">
                        <span className="text-chalk">{p.name}</span>
                        {p.pos && <span className="ml-auto font-mono text-xs text-mist">{p.pos}</span>}
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Infirmerie & suspensions */}
      {d.absences && (d.absences.home.length > 0 || d.absences.away.length > 0) && (
        <div className="mt-8 rounded-card border border-line bg-slate p-5">
          <h2 className="mb-1 text-xs font-semibold uppercase tracking-wider text-mist">
            Infirmerie & suspensions
          </h2>
          <p className="mb-4 text-xs text-mist">
            Indicatif — n&apos;ajuste pas encore les buts attendus du modèle (contrairement
            aux sélections, où la dépendance par buteur est calculée).
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            {(["home", "away"] as const).map((side) => {
              const list = d.absences![side];
              const teamName = side === "home" ? d.home_team : d.away_team;
              const accent = side === "home" ? "pitch" : "clay";
              return (
                <div key={side} className="rounded-md border border-line bg-ink/40 p-4">
                  <div className={`mb-2 font-display text-lg font-semibold text-${accent}`}>{teamName}</div>
                  {list.length === 0 ? (
                    <p className="text-sm text-mist">Aucun forfait déclaré.</p>
                  ) : (
                    <div className="space-y-1.5">
                      {list.map((p, i) => (
                        <div key={i} className="flex items-center justify-between border-b border-line/30 py-1 text-sm">
                          <span className="text-chalk">{p.name}</span>
                          {p.reason && (
                            <span className="rounded border border-clay/40 px-2 py-0.5 text-xs text-clay">{p.reason}</span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Classement + H2H */}
      <div className="mt-8 grid gap-8 lg:grid-cols-2">
        <section>
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-mist">
            Au classement ({seasonLabel(d.season)})
          </h2>
          {d.standings_note ? (
            <div className="rounded-card border border-line bg-slate p-4 text-sm text-mist">
              {d.standings_note}
            </div>
          ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            <StandingCard team={d.home_team} snap={d.standings.home} accent="pitch" />
            <StandingCard team={d.away_team} snap={d.standings.away} accent="clay" />
          </div>
          )}
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

      {!d.lineups && d.fixture_id && (
        <p className="mt-8 text-xs text-mist">
          Compositions pas encore publiées (généralement ~40 min avant le coup d&apos;envoi).
        </p>
      )}
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
