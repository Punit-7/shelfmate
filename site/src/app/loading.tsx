// Shown while a page is fetching. Grey shapes in the layout of the real page, so nothing jumps.
export default function Loading() {
  return (
    <div role="status" aria-label="Loading" className="space-y-4">
      <div className="h-8 w-56 animate-pulse rounded bg-surface" />
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-5">
        {Array.from({ length: 5 }, (_, i) => (
          <div key={i} className="h-80 animate-pulse rounded-2xl border border-line bg-surface" />
        ))}
      </div>
    </div>
  );
}
