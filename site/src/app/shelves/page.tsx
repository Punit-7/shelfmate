import Cover from "@/components/Cover";
import ShelfActions from "@/components/ShelfActions";
import { getJson, type ShelfBook } from "@/lib/api";

const SHELVES = ["currently-reading", "to-read", "read"] as const;

export default async function Shelves({
  searchParams,
}: {
  searchParams: Promise<{ name?: string }>;
}) {
  const { name: asked } = await searchParams;
  const name = SHELVES.find((s) => s === asked) ?? "currently-reading";
  const books = await getJson<ShelfBook[]>(`/shelf?name=${name}`);
  return (
    <>
      <div className="flex flex-wrap gap-3">
        {SHELVES.map((s) => (
          <a
            key={s}
            href={`/shelves?name=${s}`}
            aria-current={s === name ? "page" : undefined}
            className={`rounded-lg px-3 py-1.5 ${s === name ? "bg-accent font-bold text-page" : "border border-line text-ink-2"}`}
          >
            {s}
          </a>
        ))}
      </div>
      {books.length === 0 && <p className="text-ink-3">No books on this shelf yet.</p>}
      <div className="space-y-3">
        {books.map((b) => {
          const pct = b.total_chapters ? Math.min(100, (b.chapter / b.total_chapters) * 100) : 0;
          return (
            <div key={b.book_id} className="flex flex-col gap-4 rounded-2xl border border-line bg-surface p-4 sm:flex-row sm:items-center">
              <Cover title={b.title} url={b.cover_url} className="h-24 w-16 shrink-0 rounded-md" />
              <div className="min-w-0 grow space-y-1">
                <div className="font-bold">{b.title}</div>
                <div className="text-sm text-ink-2">{b.author}</div>
                {name === "currently-reading" && (
                  <>
                    <div className="h-2 rounded bg-line">
                      <div className="h-2 rounded bg-accent" style={{ width: `${pct}%` }} />
                    </div>
                    <div className="text-xs text-ink-3">
                      {b.total_chapters ? `Chapter ${b.chapter} of ${b.total_chapters}` : `Chapter ${b.chapter}`}
                    </div>
                  </>
                )}
                {name === "read" && (
                  <div className="text-sm text-ink-3">{b.rating ? "★".repeat(b.rating) : "Not rated"}</div>
                )}
              </div>
              <ShelfActions key={`${b.book_id}-${b.chapter}-${b.total_chapters}`} book={b} shelf={name} />
            </div>
          );
        })}
      </div>
    </>
  );
}
