import Link from "next/link";

const links = [
  { href: "/", label: "Accueil" },
  { href: "/upcoming", label: "Matchs à venir" },
  { href: "/match", label: "Dossier de match" },
  { href: "/clubs", label: "Championnats" },
  { href: "/predict", label: "Prédire un match" },
  { href: "/teams", label: "Classement" },
  { href: "/model", label: "Performance" },
];

export function Nav() {
  return (
    <header className="sticky top-0 z-20 border-b border-line bg-ink/85 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-3.5">
        <Link href="/" className="flex items-center gap-2.5">
          <span className="grid h-7 w-7 place-items-center rounded-md bg-pitch/15 font-mono text-sm font-bold text-pitch">
            P
          </span>
          <span className="font-display text-lg font-bold tracking-tight text-chalk">
            Pitch
          </span>
        </Link>
        <nav className="flex items-center gap-1 text-sm">
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className="rounded-md px-3 py-1.5 text-mist transition-colors hover:bg-slate hover:text-chalk"
            >
              {l.label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
