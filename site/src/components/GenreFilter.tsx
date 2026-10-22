import Link from "next/link";

// One chip per genre found in the recommendations. Choosing one reloads the page with ?genre=...
export default function GenreFilter({ genres, active }: { genres: string[]; active?: string }) {
  if (genres.length === 0) return null;
  const chip = "rounded-full border px-3 py-1 text-sm";
  const on = "border-accent bg-accent font-bold text-page";
  const off = "border-line text-ink-2 hover:text-ink";
  return (
    <nav aria-label="Filter by genre" className="flex flex-wrap items-center gap-2">
      <span className="text-sm text-ink-3">Genre</span>
      <Link href="/" aria-current={!active ? "true" : undefined} className={`${chip} ${!active ? on : off}`}>
        All
      </Link>
      {genres.map((g) => (
        <Link
          key={g}
          href={`/?genre=${encodeURIComponent(g)}`}
          aria-current={g === active ? "true" : undefined}
          className={`${chip} ${g === active ? on : off}`}
        >
          {g}
        </Link>
      ))}
    </nav>
  );
}
