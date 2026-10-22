import Cover from "@/components/Cover";
import Summary from "@/components/Summary";
import type { Recommendation } from "@/lib/api";

export default function BookCard({ book }: { book: Recommendation }) {
  return (
    <div data-testid="book-card" className="flex flex-col gap-2 rounded-2xl border border-line bg-surface p-4">
      <Cover title={book.title} url={book.cover_url} className="h-48 w-full rounded-lg" />
      <div className="font-bold">{book.title}</div>
      <div className="text-sm text-ink-2">{book.author}</div>
      {book.because && <p className="text-sm text-ink-3">{book.because}</p>}
      {book.summary && <Summary text={book.summary} />}
      <div className="mt-auto flex flex-wrap gap-2 pt-2">
        {book.shops.map((s) => (
          <a
            key={s.store}
            href={s.url}
            target="_blank"
            rel="noreferrer"
            className="rounded-lg border border-line px-3 py-1.5 text-xs text-accent hover:text-ink"
          >
            {s.store}
          </a>
        ))}
      </div>
    </div>
  );
}
