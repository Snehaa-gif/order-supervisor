import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import Link from "next/link";
import { Suspense } from "react";
import { ApiHealthBanner } from "@/components/shell/ApiHealthBanner";
import { MainNav, MainNavFallback } from "@/components/shell/MainNav";
import { ToastProvider } from "@/components/ui/Toaster";
import "./globals.css";

const plexSans = IBM_Plex_Sans({
  variable: "--font-plex-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

const plexMono = IBM_Plex_Mono({
  variable: "--font-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Order Supervisor",
  description: "Long-running AI supervisors for e-commerce orders, orchestrated with Temporal.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${plexSans.variable} ${plexMono.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        <ToastProvider>
          <header className="sticky top-0 z-40 border-b border-rule bg-paper/90 backdrop-blur">
            <div className="mx-auto flex h-14 max-w-[1360px] items-center justify-between gap-4 px-6">
              <Link href="/" className="group flex items-baseline gap-2">
                <span className="grid h-6 w-6 place-items-center rounded-[5px] bg-ink font-mono text-[11px] font-medium text-paper transition-colors group-hover:bg-signal">
                  OS
                </span>
                <span className="text-[15px] font-semibold tracking-tight">Order Supervisor</span>
                <span className="hidden font-mono text-[11px] text-ink-3 md:inline">temporal · fastapi · gemini</span>
              </Link>
              <Suspense fallback={<MainNavFallback />}>
                <MainNav />
              </Suspense>
            </div>
          </header>
          <ApiHealthBanner />
          <main className="mx-auto w-full max-w-[1360px] flex-1 px-6 pb-16 pt-8">{children}</main>
        </ToastProvider>
      </body>
    </html>
  );
}
