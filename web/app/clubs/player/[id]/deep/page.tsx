import Link from "next/link";
import { players } from "@/lib/api";

export const dynamic = "force-dynamic";

function seasonLabel(s: number) {
  return `${s}-${String(s + 1).slice(-2)}`;
}

export default async function PlayerDeepPage({
  params,
  searchParams,
}: {
  params: { id: string };
  searchParams: { season?: string; team?: string; name?: string };
}) {
  const season = Number(searchParams.season) || 2025;
  const team = searchParams.team ?? "";
  const name = searchParams.name;
  const id = Number(params.id);

  const deep = team
    ? await players.deep(id, season, team, name).catch(() => null)
    : null;

  return (
    <div>
      <Link href={`/clubs/player/${id}?season=${season}`} className="mb-5 inline-block text-sm text-pitch hover:underline">
        ← Fiche joueur
      </Link>

      <header className="mb-8">
        <p className="mb-2 font-mono text-xs uppercase tracking-widest text-pitch">Analyse approfondie</p>
        <h1 className="font-display text-3xl font-bold tracking-tight sm:text-4xl">
          {name ?? "Joueur"} <span className="text-mist">— {team} · {seasonLabel(season)}</span>
        </h1>
        <p className="mt-2 max-w-2xl text-mist">
          Construit depuis les événements de tous les matchs de l&apos;équipe sur la saison.
          Le premier calcul peut prendre un moment (chaque match est ensuite gardé en cache) ;
          si la page expire, recharge-la : le calcul reprend là où il s&apos;était arrêté.
        </p>
      </header>

      {!deep ? (
        <div className="rounded-card border border-line bg-slate p-8 text-center text-mist">
          Analyse indisponible : aucun match trouvé pour « {team} » sur {seasonLabel(season)} dans
          les données importées (vérifie que la ligue/saison a été synchronisée avec{" "}
          <code className="font-mono text-chalk">results</code>), ou premier calcul interrompu — recharge la page.
        </div>
      ) : (
        <>
          {/* Chiffres clés */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Kpi label="Buts sur la saison analysée" value={String(deep.goals_total)} sub={deep.penalties > 0 ? `dont ${deep.penalties} pen.` : undefined} />
            <Kpi label="Passes décisives" value={String(deep.assists_total)} />
            <Kpi label="Matchs avec au moins un but" value={`${deep.matches_with_goal}/${deep.analyzed_matches}`} />
            <Kpi label="Domicile / Extérieur" value={`${deep.venue.home} / ${deep.venue.away}`} />
          </div>

          {deep.missing_matches > 0 && (
            <p className="mt-3 text-xs text-signal">
              {deep.missing_matches} match(s) n&apos;ont pas pu être récupérés — recharge la page pour compléter.
            </p>
          )}

          <div className="mt-8 grid gap-8 lg:grid-cols-2">
            {/* Par adversaire */}
            <section>
              <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-mist">
                Contre quelles équipes il marque
              </h2>
              <div className="rounded-card border border-line bg-slate p-4">
                {deep.by_opponent.filter((o) => o.goals > 0 || o.assists > 0).length === 0 ? (
                  <p className="text-center text-sm text-mist">Aucun but ni passe sur la saison analysée.</p>
                ) : (
                  <div className="space-y-2">
                    {deep.by_opponent
                      .filter((o) => o.goals > 0 || o.assists > 0)
                      .map((o) => {
                        const max = Math.max(...deep.by_opponent.map((x) => x.goals), 1);
                        return (
                          <div key={o.opponent} className="flex items-center gap-3 text-sm">
                            <span className="w-40 shrink-0 truncate text-chalk">{o.opponent}</span>
                            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-line">
                              <div className="h-full rounded-full bg-pitch" style={{ width: `${(o.goals / max) * 100}%` }} />
                            </div>
                            <span className="w-24 shrink-0 text-right font-mono text-xs tabular text-chalk">
                              {o.goals} but{o.goals > 1 ? "s" : ""}
                              {o.assists > 0 && <span className="text-mist"> +{o.assists}p</span>}
                            </span>
                          </div>
                        );
                      })}
                  </div>
                )}
                <p className="mt-3 text-xs text-mist">Sur {deep.analyzed_matches} matchs analysés · p = passes décisives.</p>
              </div>
            </section>

            {/* Par tranche de minutes */}
            <section>
              <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-mist">
                À quel moment du match
              </h2>
              <div className="rounded-card border border-line bg-slate p-4">
                <div className="flex h-40 items-end gap-2">
                  {deep.by_minute.map((b) => {
                    const max = Math.max(...deep.by_minute.map((x) => x.goals), 1);
                    return (
                      <div key={b.bucket} className="flex flex-1 flex-col items-center gap-1.5">
                        <span className="font-mono text-xs tabular text-chalk">{b.goals || ""}</span>
                        <div
                          className="w-full rounded-t bg-signal/80"
                          style={{ height: `${(b.goals / max) * 100}%`, minHeight: b.goals > 0 ? "6px" : "2px", opacity: b.goals > 0 ? 1 : 0.25 }}
                        />
                        <span className="font-mono text-[10px] text-mist">{b.bucket}</span>
                      </div>
                    );
                  })}
                </div>
                <p className="mt-3 text-xs text-mist">Répartition des buts par tranche de minutes.</p>
              </div>
            </section>
          </div>
        </>
      )}
    </div>
  );
}

function Kpi({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-card border border-line bg-slate p-4">
      <div className="font-mono text-2xl font-bold tabular text-chalk">
        {value}
        {sub && <span className="ml-2 text-xs font-normal text-mist">{sub}</span>}
      </div>
      <div className="mt-1 text-xs text-mist">{label}</div>
    </div>
  );
}
