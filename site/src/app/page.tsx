import AskBox from "@/components/AskBox";
import BookCard from "@/components/BookCard";
import GenreFilter from "@/components/GenreFilter";
import MoreBooks from "@/components/MoreBooks";
import Refresher from "@/components/Refresher";
import { getJson, type LaneName, type Lanes } from "@/lib/api";

export const metadata = { title: "Recommendations" };

function Lane({ title, lane, lanes, genre }: { title: string; lane: LaneName; lanes: Lanes; genre?: string }) {
  const books = lanes[lane];
  return (
    <section className="space-y-4">
      <h2 className="text-2xl font-bold">{title}</h2>
      {books.length === 0 && <p className="text-ink-3">{genre ? `No ${genre} books here.` : "Nothing here yet."}</p>}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-5">
        {books.map((b) => (
          <BookCard key={b.book_id} book={b} />
        ))}
      </div>
      <MoreBooks lane={lane} start={books.length} total={lanes.total[lane]} genre={genre} />
    </section>
  );
}

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ finished?: string; genre?: string }>;
}) {
  const { finished, genre } = await searchParams;
  const lanes = await getJson<Lanes>(`/recommendations${genre ? `?genre=${encodeURIComponent(genre)}` : ""}`);
  return (
    <>
      {finished && (
        <p role="status" className="rounded-xl border border-line bg-surface p-4 text-ink-2">
          Saved. Your recommendations are being updated, and this page refreshes by itself.
        </p>
      )}
      <AskBox />
      <Refresher busy={lanes.busy} />
      <GenreFilter genres={lanes.genres} active={genre} />
      <Lane title="Continue your series" lane="continue" lanes={lanes} genre={genre} />
      <Lane title="Try something new" lane="new" lanes={lanes} genre={genre} />
    </>
  );
}
