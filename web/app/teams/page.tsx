import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function TeamsPage() {
  const teams = (await api.teams()).filter((t) => t.elo !== null).slice(0, 60);

  const maxAtt = Math.max(...teams.map((t) => t.attack ?? 0));
  const minDef = Math.min(...teams.map((t) => t.defense ?? 99));
  const maxDef = Math.max(...teams.map((t) => t.defense ?? 0));

  return (
    <div>
      <header className="mb-8">
        <p className="mb-2 font-mono text-xs uppercase tracking-widest text-pitch">
          Forces d&apos;équipe
        </p>
        <h1 className="font-display text-3xl font-bold tracking-tight sm:text-4xl">
          Classement du modèle
        </h1>
        <p className="mt-2 max-w-2xl text-mist">
          Note ELO dynamique (hiérarchie globale) et paramètres Dixon-Coles :
          attaque α (plus haut = meilleur) et défense β (plus bas = meilleur).
        </p>
      </header>

      <div className="overflow-hidden rounded-card border border-line">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line bg-slate text-left text-xs uppercase tracking-wider text-mist">
              <th className="px-4 py-3 font-medium">#</th>
              <th className="px-4 py-3 font-medium">Équipe</th>
              <th className="px-4 py-3 text-right font-medium">ELO</th>
              <th className="px-4 py-3 font-medium">Attaque</th>
              <th className="px-4 py-3 font-medium">Défense</th>
            </tr>
          </thead>
          <tbody>
            {teams.map((t, i) => (
              <tr
                key={t.team}
                className="border-b border-line/50 transition-colors hover:bg-slate/60"
              >
                <td className="px-4 py-2.5 font-mono text-mist">{i + 1}</td>
                <td className="px-4 py-2.5 font-medium text-chalk">{t.team}</td>
                <td className="px-4 py-2.5 text-right font-mono tabular text-chalk">
                  {t.elo?.toFixed(0)}
                </td>
                <td className="px-4 py-2.5">
                  <MiniBar value={(t.attack ?? 0) / maxAtt} color="#22C77E" label={t.attack?.toFixed(2)} />
                </td>
                <td className="px-4 py-2.5">
                  {/* Défense : inversée (β bas = barre pleine) */}
                  <MiniBar
                    value={1 - ((t.defense ?? 0) - minDef) / (maxDef - minDef)}
                    color="#3B82F6"
                    label={t.defense?.toFixed(2)}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function MiniBar({ value, color, label }: { value: number; color: string; label?: string }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-line">
        <div
          className="h-full rounded-full"
          style={{ width: `${Math.max(4, value * 100)}%`, backgroundColor: color }}
        />
      </div>
      <span className="font-mono text-xs tabular text-mist">{label}</span>
    </div>
  );
}
