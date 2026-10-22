"use client";
import Link, { useLinkStatus } from "next/link";
import { usePathname } from "next/navigation";
import Spinner from "@/components/Spinner";

const links = [
  ["/", "Recommendations"],
  ["/shelves", "My shelves"],
  ["/add", "Add a book"],
  ["/dashboard", "Dashboard"],
];

// Must sit inside a Link: it spins while that link's page is loading.
function Pending() {
  const { pending } = useLinkStatus();
  return pending ? <Spinner className="ml-2 size-3" /> : null;
}

export default function Nav() {
  const path = usePathname();
  return (
    <nav className="flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-line px-4 py-4 md:px-10">
      <span className="grow text-xl font-bold">Shelfmate</span>
      {links.map(([href, label]) => {
        const active = href === "/" ? path === "/" : path.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={active ? "font-bold text-ink underline decoration-accent underline-offset-8" : "text-ink-2 hover:text-ink"}
          >
            {label}
            <Pending />
          </Link>
        );
      })}
    </nav>
  );
}
