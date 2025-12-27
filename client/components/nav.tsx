import Link from "next/link";

const links = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/sentiment", label: "Sentiment" },
  { href: "/legislation", label: "Legislation" },
  { href: "/strategy", label: "Strategy" },
  { href: "/vegas-intel", label: "Vegas Intel" },
];

export function TopNav() {
  return (
    <nav className="w-full border-b border-white/5 bg-app-bg">
      <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-4">
        <div className="text-sm font-semibold tracking-wide text-text-primary">
          ZL Intelligence
        </div>
        <div className="flex items-center gap-6 text-sm text-text-tertiary">
          {links.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="transition-colors hover:text-text-primary"
            >
              {link.label}
            </Link>
          ))}
        </div>
      </div>
    </nav>
  );
}
