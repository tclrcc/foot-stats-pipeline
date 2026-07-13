"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

const groups = [
  {
    label: "Sélections",
    links: [
      { href: "/upcoming", label: "Matchs à venir" },
      { href: "/match", label: "Dossier de match" },
      { href: "/predict", label: "Prédire un match" },
      { href: "/teams", label: "Classement" },
      { href: "/model", label: "Performance" },
    ],
  },
  {
    label: "Clubs",
    links: [
      { href: "/clubs", label: "Championnats" },
      { href: "/clubs/predict", label: "Prédire un match" },
      { href: "/clubs/search", label: "Rechercher un joueur" },
    ],
  },
];

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(href + "/");
}

export function Nav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [menuGroup, setMenuGroup] = useState<string | null>(null);

  return (
    <header className="sticky top-0 z-20 border-b border-line bg-ink/85 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-3.5">
        <Link href="/" className="flex items-center gap-2.5" onClick={() => setOpen(false)}>
          <span className="grid h-7 w-7 place-items-center rounded-md bg-pitch/15 font-mono text-sm font-bold text-pitch">
            P
          </span>
          <span className="font-display text-lg font-bold tracking-tight text-chalk">Pitch</span>
        </Link>

        {/* Nav desktop : groupée par onglets déroulants */}
        <nav className="hidden items-center gap-1 text-sm md:flex">
          {groups.map((g) => {
            const groupActive = g.links.some((l) => isActive(pathname, l.href));
            return (
              <div
                key={g.label}
                className="relative"
                onMouseEnter={() => setMenuGroup(g.label)}
                onMouseLeave={() => setMenuGroup(null)}
              >
                <button
                  className={`rounded-md px-3 py-1.5 transition-colors ${
                    groupActive ? "text-pitch" : "text-mist hover:bg-slate hover:text-chalk"
                  }`}
                >
                  {g.label}
                </button>
                {menuGroup === g.label && (
                  <div className="absolute left-0 top-full pt-1">
                    <div className="w-52 rounded-md border border-line bg-slate p-1.5 shadow-lg">
                      {g.links.map((l) => (
                        <Link
                          key={l.href}
                          href={l.href}
                          className={`block rounded px-3 py-2 text-sm transition-colors ${
                            isActive(pathname, l.href)
                              ? "bg-pitch/10 text-pitch"
                              : "text-mist hover:bg-ink hover:text-chalk"
                          }`}
                        >
                          {l.label}
                        </Link>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </nav>

        {/* Bouton menu mobile */}
        <button
          onClick={() => setOpen((v) => !v)}
          aria-label="Menu"
          className="grid h-9 w-9 place-items-center rounded-md border border-line text-chalk md:hidden"
        >
          {open ? (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          ) : (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 6h18M3 12h18M3 18h18" />
            </svg>
          )}
        </button>
      </div>

      {/* Menu mobile déplié */}
      {open && (
        <nav className="border-t border-line px-5 pb-4 pt-2 md:hidden">
          {groups.map((g) => (
            <div key={g.label} className="mb-3">
              <p className="mb-1 px-1 font-mono text-xs uppercase tracking-widest text-mist">
                {g.label}
              </p>
              <div className="space-y-0.5">
                {g.links.map((l) => (
                  <Link
                    key={l.href}
                    href={l.href}
                    onClick={() => setOpen(false)}
                    className={`block rounded-md px-3 py-2 text-sm ${
                      isActive(pathname, l.href) ? "bg-pitch/10 text-pitch" : "text-mist"
                    }`}
                  >
                    {l.label}
                  </Link>
                ))}
              </div>
            </div>
          ))}
        </nav>
      )}
    </header>
  );
}
