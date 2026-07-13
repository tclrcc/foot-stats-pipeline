export default function Loading() {
  return (
    <div className="animate-pulse">
      <div className="mb-5 h-4 w-32 rounded bg-slate" />
      <div className="mb-2 h-3 w-40 rounded bg-slate" />
      <div className="mb-3 h-9 w-96 max-w-full rounded bg-slate" />
      <div className="mb-8 h-4 w-full max-w-xl rounded bg-slate" />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="rounded-card border border-line bg-slate p-4">
            <div className="h-7 w-16 rounded bg-ink" />
            <div className="mt-2 h-3 w-24 rounded bg-ink" />
          </div>
        ))}
      </div>

      <p className="mt-6 text-center text-sm text-mist">
        Calcul en cours — première analyse de cette équipe cette saison, ça peut
        prendre jusqu&apos;à 30 secondes. Les suivantes seront instantanées.
      </p>

      <div className="mt-8 grid gap-8 lg:grid-cols-2">
        <div className="h-64 rounded-card border border-line bg-slate" />
        <div className="h-64 rounded-card border border-line bg-slate" />
      </div>
    </div>
  );
}
