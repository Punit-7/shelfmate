import Cover from "@/components/Cover";
import { getJson } from "@/lib/api";

type Recent = {
  book_id: number;
  title: string;
  cover_url: string | null;
  rating: number;
  community: number | null;
};

type Stats = {
  shelves: Record<string, number>;
  ratings: Record<string, number>;
  catalogue: number;
  recent: Recent[];
};

async function apiIsHealthy() {
  try {
    await getJson("/health");
    return true;
  } catch {
    return false;
  }
}

export default async function Dashboard() {
  const [stats, healthy] = await Promise.all([getJson<Stats>("/stats"), apiIsHealthy()]);
  const tiles = [
    ["Books in catalogue", stats.catalogue],
    ["Read", stats.shelves["read"] ?? 0],
    ["Reading", stats.shelves["currently-reading"] ?? 0],
    ["To read", stats.shelves["to-read"] ?? 0],
  ];
  const most = Math.max(1, ...Object.values(stats.ratings));

  return (
    <>
      <h1 className="text-3xl font-bold">Dashboard</h1>
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {tiles.map(([label, value]) => (
          <div key={label} className="rounded-2xl border border-line bg-surface p-5">
            <div className="text-xs uppercase tracking-wider text-ink-3">{label}</div>
            <div className="mt-1 text-3xl font-bold">{value.toLocaleString("en-US")}</div>
          </div>
        ))}
      </div>
      <section className="rounded-2xl border border-line bg-surface p-6">
        <h2 className="mb-4 text-lg font-bold">How you rate</h2>
        <div className="flex h-48 items-end gap-4 border-b border-line">
          {[1, 2, 3, 4, 5].map((star) => {
            const n = stats.ratings[star] ?? 0;
            return (
              <div key={star} className="flex h-full flex-1 flex-col items-center justify-end gap-1">
                <span className="text-xs text-ink-2">{n}</span>
                <div className="w-full rounded-t bg-accent" style={{ height: `${(n / most) * 100}%` }} />
              </div>
            );
          })}
        </div>
        <div className="mt-2 flex gap-4 text-center text-xs text-ink-3">
          {[1, 2, 3, 4, 5].map((s) => (
            <span key={s} className="flex-1">
              {s} {s === 1 ? "star" : "stars"}
            </span>
          ))}
        </div>
      </section>
      <section className="rounded-2xl border border-line bg-surface p-6">
        <h2 className="mb-4 text-lg font-bold">Recently finished</h2>
        {stats.recent.length === 0 ? (
          <p className="text-ink-3">No finished books yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-ink-3">
                <tr>
                  <th scope="col" className="py-2 font-normal">Book</th>
                  <th scope="col" className="py-2 font-normal">You</th>
                  <th scope="col" className="py-2 font-normal">Readers on average</th>
                </tr>
              </thead>
              <tbody>
                {stats.recent.map((b) => (
                  <tr key={b.book_id} className="border-t border-line">
                    <td className="py-3">
                      <div className="flex items-center gap-3">
                        <Cover title={b.title} url={b.cover_url} className="h-12 w-8 shrink-0 rounded" />
                        <span>{b.title}</span>
                      </div>
                    </td>
                    <td className="py-3 text-accent">{b.rating ? "★".repeat(b.rating) : "Not rated"}</td>
                    <td className="py-3 text-ink-2">{b.community === null ? "No ratings yet" : `${b.community.toFixed(2)} / 5`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <section className="rounded-2xl border border-line bg-surface p-6">
        <h2 className="mb-2 text-lg font-bold">System health</h2>
        <p className={healthy ? "text-green-400" : "text-red-400"}>
          API and database: {healthy ? "healthy" : "not answering"}
        </p>
      </section>
    </>
  );
}
