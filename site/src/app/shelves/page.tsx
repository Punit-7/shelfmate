import Link from "next/link";
import Cover from "@/components/Cover";
import ShelfActions from "@/components/ShelfActions";
import { getJson, type ShelfBook } from "@/lib/api";

export const metadata = { title: "My shelves" };

const SHELVES = ["currently-reading", "to-read", "read"] as const;

const SORTS = {
  added: "Recently added",
  title: "Title",
  author: "Author",
  rating: "Rating",
} as const;
type Sort = keyof typeof SORTS;

// The API sends a shelf newest first, so "added" keeps that order.
function arrange(books: ShelfBook[], q: string, sort: Sort) {
  const needle = q.trim().toLowerCase();
  const found = needle
    ? books.filter((b) => `${b.title} ${b.author}`.toLowerCase().includes(needle))
    : [...books];
  if (sort === "title") found.sort((a, b) => a.title.localeCompare(b.title));
  if (sort === "author") found.sort((a, b) => a.author.localeCompare(b.author));
  if (sort === "rating") found.sort((a, b) => b.rating - a.rating); // best first, unrated last
  return found;
}

export default async function Shelves({
  searchParams,
}: {
  searchParams: Promise<{ name?: string; q?: string; sort?: string }>;
}) {
  const { name: asked, q = "", sort: askedSort } = await searchParams;
  const name = SHELVES.find((s) => s === asked) ?? "currently-reading";
  const sort = (Object.keys(SORTS) as Sort[]).find((s) => s === askedSort) ?? "added";
  const all = await getJson<ShelfBook[]>(`/shelf?name=${name}`);
  const books = arrange(all, q, sort);
  const filtered = q.trim() !== "" || sort !== "added";
  return (
    <>
      <div className="flex flex-wrap gap-3">
        {SHELVES.map((s) => (
          <Link
            key={s}
            href={`/shelves?name=${s}`}
            aria-current={s === name ? "page" : undefined}
            className={`rounded-lg px-3 py-1.5 ${s === name ? "bg-accent font-bold text-page" : "border border-line text-ink-2"}`}
          >
            {s}
          </Link>
        ))}
      </div>

      {all.length > 1 && (
        <form action="/shelves" className="flex flex-wrap items-center gap-2 text-sm">
          <input type="hidden" name="name" value={name} />
          <input
            type="search"
            name="q"
            defaultValue={q}
            placeholder="Search this shelf"
            aria-label="Search this shelf"
            className="min-w-0 grow rounded-lg border border-line bg-surface px-3 py-2 sm:max-w-xs"
          />
          <select
            name="sort"
            defaultValue={sort}
            aria-label="Sort this shelf"
            className="rounded-lg border border-line bg-surface px-3 py-2"
          >
            {(Object.keys(SORTS) as Sort[]).map((s) => (
              <option key={s} value={s}>
                {SORTS[s]}
              </option>
            ))}
          </select>
          <button type="submit" className="rounded-lg border border-line px-3 py-2 text-accent">
            Apply
          </button>
          {filtered && (
            <Link href={`/shelves?name=${name}`} className="text-ink-3 hover:text-ink">
              Clear
            </Link>
          )}
        </form>
      )}

      {all.length > 0 && (
        <p className="text-sm text-ink-3" aria-live="polite">
          {books.length === all.length ? `${all.length} ${all.length === 1 ? "book" : "books"}` : `${books.length} of ${all.length} books`}
        </p>
      )}

      {all.length === 0 && (
        <p className="text-ink-3">
          No books on this shelf yet.{" "}
          {name === "read" ? (
            "Finish a book and it shows up here."
          ) : (
            <Link href="/add" className="text-accent hover:text-ink">
              Add a book
            </Link>
          )}
        </p>
      )}
      {all.length > 0 && books.length === 0 && (
        <p className="text-ink-3">
          No book matches “{q}”.{" "}
          <Link href={`/shelves?name=${name}`} className="text-accent hover:text-ink">
            Clear the search
          </Link>
        </p>
      )}

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
              </div>
              <ShelfActions key={`${b.book_id}-${b.chapter}-${b.total_chapters}-${b.rating}`} book={b} shelf={name} />
            </div>
          );
        })}
      </div>
    </>
  );
}
