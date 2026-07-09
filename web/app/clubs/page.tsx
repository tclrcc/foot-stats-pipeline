import Link from "next/link";
import { clubs, StandingRow, ClubResult } from "@/lib/api";

export const dynamic = "force-dynamic";

function fmtDate(d: string) {
  const dt = new Date(d);
  if (isNaN(dt.getTime())) return d;
  return dt.toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "numeric" });
}

function seasonLabel(s: number) {
  return `${s}-${String(s + 1).slice(-2)}`;
}

export default async function ClubsPage({
  searchParams,
}: {
  searchParams: { league?: string; season?: string; team?: string };
}) {
  const leagues = await clubs.leagues().catch(() => []);

  if (leagues.length === 0) {
    return (
      <div>
        <Header />
        <div className="rounded-card border border-line bg-slate p-8 text-center text-mist">
          Aucune donnée club importée. Lance{" "}
          <code className="font-mono text-chalk">python src/sync_api_football.py results</code>{" "}
          sur le serveur pour remplir la base.
        </div>
      </div>
    );
  }

  const leagueId = Number(searchParams.league) || leagues[0].league_id;
  const current = leagues.find((l) => l.league_id === leagueId) ?? leagues[0];
  const season = Number(searchParams.season) || current.seasons[0].season;
  const team = searchParams.team;

  const [standings, results] = await Promise.all([
    clubs.standings(current.league_id, season).catch(() => [] as StandingRow[]),
    clubs.results(current.league_id, season, team, team ? 400 : 40).catch(() => [] as ClubResult[]),
  ]);

  const base = `/clubs?league=${current.league_id}&season=${season}`;

  return (
    <div>
      <Header />

      {/* Sélecteur de championnat */}
      <div className="mb-3 flex flex-wrap gap-2">
        {leagues.map((l) => (
          <Link
            key={l.league_id}
            href={`/clubs?league=${l.league_id}`}
            className={`rounded-md border px-3 py-1.5 text-sm transition-colors ${
              l.league_id === current.league_id
                ? "border-pitch bg-pitch/10 text-pitch"
                : "border-line text-mist hover:border-mist"
            }`}
          >
            {l.league_name}
          </Link>
        ))}
      </div>

      {/* Sélecteur de saison */}
      <div className="mb-8 flex flex-wrap gap-2">
        {current.seasons.map((s) => (
          <Link
            key={s.season}
            href={`/clubs?league=${current.league_id}&season=${s.season}`}
            className={`rounded border px-2.5 py-1 font-mono text-xs tabular transition-colors ${
              s.season === season
                ? "border-signal bg-signal/10 text-signal"
                : "border-line text-mist hover:border-mist"
            }`}
            title={`${s.matches} matchs`}
          >
            {seasonLabel(s.season)}
          </Link>
        ))}
      </div>

      <div className="grid gap-8 lg:grid-cols-[1.2fr_1fr]">
        {/* Classement */}
        <section>
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-mist">
            Classement — {current.league_name} {seasonLabel(season)}
          </h2>
          <div className="overflow-x-auto rounded-card border border-line bg-slate">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line text-left font-mono text-xs uppercase text-mist">
                  <th className="px-3 py-2.5">#</th>
                  <th className="px-2 py-2.5">Équipe</th>
                  <th className="px-2 py-2.5 text-center" title="Matchs joués">MJ</th>
                  <th className="hidden px-2 py-2.5 text-center sm:table-cell">V</th>
                  <th className="hidden px-2 py-2.5 text-center sm:table-cell">N</th>
                  <th className="hidden px-2 py-2.5 text-center sm:table-cell">D</th>
                  <th className="hidden px-2 py-2.5 text-center md:table-cell">Buts</th>
                  <th className="px-2 py-2.5 text-center">Diff</th>
                  <th className="px-2 py-2.5 text-center">Pts</th>
                  <th className="hidden px-3 py-2.5 md:table-cell">Forme</th>
                </tr>
              </thead>
              <tbody className="font-mono tabular">
                {standings.map((r) => (
                  <tr
                    key={r.team}
                    className={`border-b border-line/40 transition-colors hover:bg-ink/40 ${
                      team === r.team ? "bg-pitch/5" : ""
                    }`}
                  >
                    <td className="px-3 py-2 text-mist">{r.rank}</td>
                    <td className="px-2 py-2">
                      <Link
                        href={`${base}&team=${encodeURIComponent(r.team)}`}
                        className={`font-sans font-medium hover:text-pitch ${
                          team === r.team ? "text-pitch" : "text-chalk"
                        }`}
                      >
                        {r.team}
                      </Link>
                    </td>
                    <td className="px-2 py-2 text-center text-mist">{r.played}</td>
                    <td className="hidden px-2 py-2 text-center text-mist sm:table-cell">{r.won}</td>
                    <td className="hidden px-2 py-2 text-center text-mist sm:table-cell">{r.drawn}</td>
                    <td className="hidden px-2 py-2 text-center text-mist sm:table-cell">{r.lost}</td>
                    <td className="hidden px-2 py-2 text-center text-mist md:table-cell">{r.gf}:{r.ga}</td>
                    <td className={`px-2 py-2 text-center ${r.gd > 0 ? "text-pitch" : r.gd < 0 ? "text-clay" : "text-mist"}`}>
                      {r.gd > 0 ? `+${r.gd}` : r.gd}
                    </td>
                    <td className="px-2 py-2 text-center font-semibold text-chalk">{r.points}</td>
                    <td className="hidden px-3 py-2 md:table-cell">
                      <span className="flex gap-1">
                        {r.form.map((f, i) => (
                          <span
                            key={i}
                            className={`grid h-4 w-4 place-items-center rounded-sm text-[10px] font-bold text-ink ${
                              f === "V" ? "bg-pitch" : f === "N" ? "bg-royal" : "bg-clay"
                            }`}
                          >
                            {f}
                          </span>
                        ))}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-mist">
            Classement recalculé depuis les résultats. Départage simplifié (points, différence,
            buts marqués) — les règles officielles varient selon les championnats.
          </p>
        </section>

        {/* Résultats */}
        <section>
          <div className="mb-3 flex items-baseline justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-mist">
              {team ? `Matchs — ${team}` : "Derniers résultats"}
            </h2>
            {team && (
              <Link href={base} className="text-xs text-pitch hover:underline">
                Toute la ligue →
              </Link>
            )}
          </div>
          <div className="space-y-1.5">
            {results.length === 0 && (
              <div className="rounded-card border border-line bg-slate p-6 text-center text-sm text-mist">
                Aucun résultat sur cette sélection.
              </div>
            )}
            {results.map((m, i) => {
              const homeWin = m.home_score > m.away_score;
              const awayWin = m.away_score > m.home_score;
              return (
                <div key={i} className="flex items-center gap-3 rounded-card border border-line bg-slate px-4 py-2.5">
                  <div className="w-24 shrink-0 text-xs text-mist">
                    {m.round && <div className="font-mono text-signal">{m.round}</div>}
                    {fmtDate(m.date)}
                  </div>
                  <div className="grid flex-1 grid-cols-[1fr_auto_1fr] items-center gap-2 text-sm">
                    <span className={`truncate text-right ${homeWin ? "font-semibold text-chalk" : "text-mist"}`}>
                      {m.home_team}
                    </span>
                    <span className="rounded bg-ink px-2 py-0.5 font-mono text-sm tabular text-chalk">
                      {m.home_score}–{m.away_score}
                    </span>
                    <span className={`truncate ${awayWin ? "font-semibold text-chalk" : "text-mist"}`}>
                      {m.away_team}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      </div>
    </div>
  );
}

function Header() {
  return (
    <header className="mb-8">
      <p className="mb-2 font-mono text-xs uppercase tracking-widest text-pitch">Club</p>
      <h1 className="font-display text-3xl font-bold tracking-tight sm:text-4xl">Championnats</h1>
      <p className="mt-2 max-w-2xl text-mist">
        Classements et résultats des 5 grands championnats européens, recalculés depuis les
        données importées. Clique sur une équipe pour filtrer ses matchs.
      </p>
    </header>
  );
}
