import { api } from "@/lib/api";
import { CalibrationChart } from "@/components/CalibrationChart";

export const dynamic = "force-dynamic";

// Points de calibration issus du backtest walk-forward (10 tranches).
// Servis en dur ici car l'API expose l'ECE agrégé ; la table détaillée
// pourra être ajoutée à l'endpoint /model/performance ultérieurement.
const CALIBRATION_POINTS = [
  { predicted: 5.0, observed: 3.6 },
  { predicted: 15.1, observed: 12.0 },
  { predicted: 25.4, observed: 26.5 },
  { predicted: 34.3, observed: 34.6 },
  { predicted: 44.3, observed: 38.9 },
  { predicted: 54.7, observed: 53.5 },
  { predicted: 64.6, observed: 76.2 },
  { predicted: 75.1, observed: 78.4 },
  { predicted: 84.7, observed: 88.4 },
  { predicted: 95.1, observed: 96.6 },
];

export default async function ModelPage() {
  const [perf, info] = await Promise.all([
    api.modelPerformance(),
    api.modelInfo(),
  ]);

  return (
    <div>
      <header className="mb-8">
        <p className="mb-2 font-mono text-xs uppercase tracking-widest text-pitch">
          Transparence
        </p>
        <h1 className="font-display text-3xl font-bold tracking-tight sm:text-4xl">
          Performance du modèle
        </h1>
        <p className="mt-2 max-w-2xl text-mist">
          Validé en walk-forward : à chaque mois testé, le modèle est ré-estimé
          uniquement sur les données antérieures — aucune fuite. Un modèle honnête
          montre sa précision.
        </p>
      </header>

      {perf.available ? (
        <>
          <div className="grid gap-4 sm:grid-cols-4">
            <Metric label="Brier score" value={perf.brier!.toFixed(3)} hint="↓ plus bas = mieux" accent="pitch" />
            <Metric label="Log-loss" value={perf.log_loss!.toFixed(3)} hint="↓ plus bas = mieux" accent="pitch" />
            <Metric label="Précision" value={`${perf.accuracy!.toFixed(1)}%`} hint="issue la + probable" accent="chalk" />
            <Metric label="Erreur de calib. (ECE)" value={`${perf.ece!.toFixed(2)}%`} hint="↓ plus bas = mieux" accent="signal" />
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-[auto_1fr]">
            <div className="rounded-card border border-line bg-slate p-5">
              <h3 className="mb-4 text-xs font-semibold uppercase tracking-wider text-mist">
                Diagramme de fiabilité
              </h3>
              <CalibrationChart points={CALIBRATION_POINTS} />
            </div>
            <div className="rounded-card border border-line bg-slate p-5">
              <h3 className="mb-4 text-xs font-semibold uppercase tracking-wider text-mist">
                Lecture
              </h3>
              <p className="text-sm leading-relaxed text-mist">
                Chaque point compare la probabilité <span className="text-pitch">prédite</span> par
                le modèle à la fréquence <span className="text-chalk">réellement observée</span>.
                Plus les points collent à la diagonale ambre, mieux le modèle est calibré :
                quand il annonce 30 %, l&apos;événement arrive environ 30 % du temps.
              </p>
              <p className="mt-4 text-sm leading-relaxed text-mist">
                Sur la fenêtre de test, l&apos;erreur de calibration moyenne est de{" "}
                <span className="font-mono text-signal">{perf.ece!.toFixed(2)}%</span>, et le
                Brier score bat de <span className="font-mono text-pitch">~25%</span> un modèle
                naïf basé sur les fréquences de base. C&apos;est ce qui rend les prédictions
                exploitables.
              </p>
              <p className="mt-4 font-mono text-xs text-mist">
                Dernier backtest : {perf.run_date}
              </p>
            </div>
          </div>
        </>
      ) : (
        <div className="rounded-card border border-signal/40 bg-signal/10 p-5 text-sm text-signal">
          {perf.message || "Backtest non disponible."}
        </div>
      )}

      {/* Hyperparamètres */}
      <div className="mt-6 rounded-card border border-line bg-slate p-5">
        <h3 className="mb-4 text-xs font-semibold uppercase tracking-wider text-mist">
          Paramètres du modèle
        </h3>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 text-sm">
          <Param label="γ avantage terrain" value={info.gamma.toFixed(3)} />
          <Param label="ρ correction DC" value={info.rho.toFixed(3)} />
          <Param label="ξ décroissance/j" value={info.xi_per_day.toString()} />
          <Param label="Équipes couvertes" value={info.n_teams.toString()} />
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value, hint, accent }: { label: string; value: string; hint: string; accent: string }) {
  return (
    <div className="rounded-card border border-line bg-slate p-4">
      <div className="text-xs uppercase tracking-wider text-mist">{label}</div>
      <div className={`mt-2 font-mono text-3xl font-bold tabular text-${accent}`}>{value}</div>
      <div className="mt-1 text-xs text-mist">{hint}</div>
    </div>
  );
}

function Param({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-mist">{label}</div>
      <div className="mt-1 font-mono text-lg tabular text-chalk">{value}</div>
    </div>
  );
}
