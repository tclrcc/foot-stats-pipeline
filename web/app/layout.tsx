import type { Metadata } from "next";
import { Space_Grotesk, Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { Nav } from "@/components/Nav";

const display = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-display",
  display: "swap",
});
const body = Inter({
  subsets: ["latin"],
  variable: "--font-body",
  display: "swap",
});
const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Pitch — Analyse & prédiction de football",
  description:
    "Plateforme d'analyse de football : modèle Dixon-Coles calibré, notes de force d'équipe, prédictions de matchs et distributions de scores.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="fr" className={`${display.variable} ${body.variable} ${mono.variable}`}>
      <body className="font-sans antialiased">
        <Nav />
        <main className="mx-auto max-w-6xl px-5 pb-24 pt-8">{children}</main>
        <footer className="border-t border-line">
          <div className="mx-auto max-w-6xl px-5 py-8 text-xs text-mist">
            Modèle Dixon-Coles estimé par maximum de vraisemblance · ELO dynamique ·
            calibration walk-forward. Données publiques. Projet personnel.
          </div>
        </footer>
      </body>
    </html>
  );
}
