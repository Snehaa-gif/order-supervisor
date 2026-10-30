"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Runs", match: (path: string) => path === "/" || (path.startsWith("/runs/") && path !== "/runs/new") },
  { href: "/supervisors", label: "Supervisors", match: (path: string) => path.startsWith("/supervisors") },
];

/** Navigation with the active link highlighted (reads the URL, so render it inside <Suspense>). */
export function MainNav() {
  return <NavLinks pathname={usePathname()} />;
}

/** Static navigation used while the URL-aware version streams in. */
export function MainNavFallback() {
  return <NavLinks pathname={null} />;
}

function NavLinks({ pathname }: { pathname: string | null }) {
  return (
    <nav aria-label="Main navigation" className="flex items-center gap-1">
      {LINKS.map((link) => {
        const active = pathname !== null && link.match(pathname);
        return (
          <Link
            key={link.href}
            href={link.href}
            aria-current={active ? "page" : undefined}
            className={`relative rounded-[var(--radius-control)] px-3 py-1.5 text-sm transition-colors ${
              active ? "font-semibold text-ink" : "text-ink-2 hover:bg-sunken hover:text-ink"
            }`}
          >
            {link.label}
            {active && <span className="absolute inset-x-3 -bottom-[13px] h-0.5 bg-signal" aria-hidden />}
          </Link>
        );
      })}
      <Link
        href="/runs/new"
        className="ml-3 inline-flex h-8 items-center rounded-[var(--radius-control)] bg-ink px-3 text-[13px] font-medium text-paper transition-colors hover:bg-signal"
      >
        Start a run
      </Link>
    </nav>
  );
}
