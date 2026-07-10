/* eslint-disable @next/next/no-img-element */
import Link from "next/link";
import { players, PlayerCompStats } from "@/lib/api";

export const dynamic = "force-dynamic";

const SEASONS = [2025, 2024, 2023, 2022, 2021];

function seasonLabel(s: number) {
  return `${s}-${String(s + 1).slice(-2)}`;
}

export default async function PlayerPage({
  params,
  searchParams,
}: {
  params: { id: string };
  searchParams: { season?: string };
}) {
  const season = Number(searchParams.season) || 2025;
  const p = await players.detail(Number(params.id), season).catch(() => null);

  if (!p) {
    return (
      <div>
        <Back />
        <div className="rounded-card border border-line bg-slate p-8 text-center text-mist">
          Fiche indisponible pour cette saison (joueur inconnu de l&apos;API, saison sans données,
          ou clé API absente côté serveur). Essaie une autre saison.
        </div>
        <SeasonPills id={params.id} season={season} />
      </div>
    );
  }

  return (
    <div>
      <Back />

      {/* En-tête profil */}
      <div className="rounded-card border border-line bg-slate p-6">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
          {p.photo && (
            <img
              src={p.photo}
              alt={p.name ?? ""}
              className="h-24 w-24 shrink-0 rounded-full border border-line object-cover"
            />
          )}
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="font-display text-3xl font-bold tracking-tight">
                {p.firstname && p.lastname ? `${p.firstname} ${p.lastname}` : p.name}
              </h1>
              {p.injured && (
                <span className="rounded border border-clay/40 px-2 py-0.5 text-xs text-clay">Blessé</span>
              )}
            </div>
            <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-sm text-mist">
              {p.current_team && <span>Club : <span className="text-chalk">{p.current_team}</span></span>}
              {p.nationality && <span>Nationalité : <span className="text-chalk">{p.nationality}</span></span>}
              {p.age != null && (
                <span>
                  Âge : <span className="font-mono tabular text-chalk">{p.age} ans</span>
                  {p.birth_date && <span className="text-mist"> (né le {p.birth_date}{p.birth_place ? ` à ${p.birth_place}` : ""})</span>}
                </span>
              )}
              {p.height && <span>Taille : <span className="font-mono tabular text-chalk">{p.height}</span></span>}
              {p.weight && <span>Poids : <span className="font-mono tabular text-chalk">{p.weight}</span></span>}
            </div>
          </div>
        </div>
      </div>

      <SeasonPills id={params.id} season={season} />

      {/* Analyse approfondie */}
      {p.current_team && (
        <Link
          href={`/clubs/player/${p.player_id}/deep?season=${season}&team=${encodeURIComponent(p.current_team)}&name=${encodeURIComponent(p.name ?? "")}`}
          className="mt-5 inline-block rounded-md border border-signal px-4 py-2 text-sm text-signal transition-colors hover:bg-signal hover:text-ink"
        >
          Analyse approfondie : contre qui, quand, où il marque →
        </Link>
      )}

      {/* Stats par compétition */}
      <div className="mt-6 space-y-5">
        {p.stats.length === 0 && (
          <div className="rounded-card border border-line bg-slate p-6 text-center text-sm text-mist">
            Aucune statistique sur la saison {seasonLabel(season)}.
          </div>
        )}
        {p.stats.map((st, i) => (
          <CompStats key={i} st={st} />
        ))}
      </div>

      {/* Indisponibilités */}
      {p.sidelined && p.sidelined.length > 0 && (
        <section className="mt-8">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-mist">
            Indisponibilités (blessures & suspensions)
          </h2>
          <div className="rounded-card border border-line bg-slate p-4">
            <div className="space-y-1.5">
              {p.sidelined.map((sd, i) => (
                <div key={i} className="flex items-center gap-3 border-b border-line/30 py-1.5 text-sm">
                  <span className={`shrink-0 rounded border px-2 py-0.5 text-xs ${
                    (sd.type ?? "").toLowerCase().includes("suspen")
                      ? "border-signal/40 text-signal"
                      : "border-clay/40 text-clay"
                  }`}>
                    {(sd.type ?? "").toLowerCase().includes("suspen") ? "Suspension" : "Blessure"}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-chalk">{sd.type}</span>
                  <span className="shrink-0 font-mono text-xs tabular text-mist">
                    {sd.start} → {sd.end ?? "?"}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      <div className="mt-8 grid gap-8 lg:grid-cols-2">
        {/* Parcours */}
        {p.transfers.length > 0 && (
          <section>
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-mist">Parcours</h2>
            <div className="rounded-card border border-line bg-slate p-4">
              <div className="space-y-1.5">
                {p.transfers.map((t, i) => (
                  <div key={i} className="flex items-center gap-3 border-b border-line/30 py-1.5 text-sm">
                    <span className="w-20 shrink-0 font-mono text-xs tabular text-mist">{t.date?.slice(0, 10) ?? "?"}</span>
                    <span className="min-w-0 flex-1 truncate">
                      <span className="text-mist">{t.from_team ?? "?"}</span>
                      <span className="mx-1.5 text-pitch">→</span>
                      <span className="font-medium text-chalk">{t.to_team ?? "?"}</span>
                    </span>
                    {t.type && (
                      <span className="shrink-0 rounded border border-line px-2 py-0.5 font-mono text-xs text-signal">
                        {t.type === "Free" ? "Libre" : t.type === "Loan" ? "Prêt" : t.type}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </section>
        )}

        {/* Palmarès */}
        {p.trophies.length > 0 && (
          <section>
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-mist">Palmarès</h2>
            <div className="rounded-card border border-line bg-slate p-4">
              <div className="space-y-1.5">
                {p.trophies.map((t, i) => (
                  <div key={i} className="flex items-center gap-3 border-b border-line/30 py-1.5 text-sm">
                    <span className={`shrink-0 ${t.place === "Winner" ? "" : "opacity-40 grayscale"}`}>🏆</span>
                    <span className="min-w-0 flex-1 truncate text-chalk">{t.league}</span>
                    <span className="shrink-0 text-xs text-mist">{t.country}</span>
                    <span className="w-20 shrink-0 text-right font-mono text-xs tabular text-mist">{t.season}</span>
                    <span className={`w-20 shrink-0 text-right text-xs ${t.place === "Winner" ? "text-pitch" : "text-mist"}`}>
                      {t.place === "Winner" ? "Vainqueur" : t.place === "2nd Place" ? "Finaliste/2e" : t.place}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

function CompStats({ st }: { st: PlayerCompStats }) {
  const cells: { label: string; value: string | null }[] = [
    { label: "Matchs (titulaire)", value: `${st.appearances}${st.lineups != null ? ` (${st.lineups})` : ""}` },
    { label: "Minutes", value: st.minutes != null ? String(st.minutes) : null },
    { label: "Note moyenne", value: st.rating != null ? st.rating.toFixed(2) : null },
    { label: "Buts", value: `${st.goals}${st.penalties_scored > 0 ? ` (${st.penalties_scored} pen.)` : ""}` },
    { label: "Passes décisives", value: String(st.assists) },
    { label: "Tirs (cadrés)", value: st.shots != null ? `${st.shots}${st.shots_on != null ? ` (${st.shots_on})` : ""}` : null },
    { label: "Passes clés", value: st.key_passes != null ? String(st.key_passes) : null },
    { label: "Précision passes", value: st.pass_accuracy != null ? `${st.pass_accuracy}%` : null },
    { label: "Dribbles réussis", value: st.dribbles_success != null ? `${st.dribbles_success}${st.dribbles_attempts != null ? `/${st.dribbles_attempts}` : ""}` : null },
    { label: "Tacles", value: st.tackles != null ? String(st.tackles) : null },
    { label: "Duels gagnés", value: st.duels_won != null ? `${st.duels_won}${st.duels_total != null ? `/${st.duels_total}` : ""}` : null },
    { label: "Cartons", value: `${st.yellow_cards} j.${st.red_cards > 0 ? ` / ${st.red_cards} r.` : ""}` },
  ];
  return (
    <div className="rounded-card border border-line bg-slate p-5">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <span className="font-display text-lg font-semibold text-chalk">{st.competition}</span>
          {st.team && <span className="ml-2 text-sm text-mist">— {st.team}</span>}
          {st.captain && <span className="ml-2 rounded border border-signal/40 px-1.5 py-0.5 text-xs text-signal">Capitaine</span>}
        </div>
        {st.position && <span className="font-mono text-xs text-mist">{st.position}</span>}
      </div>
      <div className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3 lg:grid-cols-4">
        {cells.filter((c) => c.value != null).map((c) => (
          <div key={c.label}>
            <div className="font-mono text-lg font-semibold tabular text-chalk">{c.value}</div>
            <div className="text-xs text-mist">{c.label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function SeasonPills({ id, season }: { id: string; season: number }) {
  return (
    <div className="mt-5 flex flex-wrap gap-2">
      {SEASONS.map((s) => (
        <Link
          key={s}
          href={`/clubs/player/${id}?season=${s}`}
          className={`rounded border px-2.5 py-1 font-mono text-xs tabular transition-colors ${
            s === season ? "border-signal bg-signal/10 text-signal" : "border-line text-mist hover:border-mist"
          }`}
        >
          {seasonLabel(s)}
        </Link>
      ))}
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
