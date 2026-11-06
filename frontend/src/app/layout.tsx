import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Vektor — Paper trading workspace",
  description: "A local-first workspace for researching and simulating trading strategies. Paper trading only.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><a className="skip-link" href="#main">Skip to content</a>{children}</body></html>;
}
