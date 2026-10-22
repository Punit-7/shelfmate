export default function Loading() {
  return (
    <div role="status" aria-label="Loading your shelves" className="space-y-3">
      <div className="h-9 w-80 animate-pulse rounded bg-surface" />
      {Array.from({ length: 3 }, (_, i) => (
        <div key={i} className="h-32 animate-pulse rounded-2xl border border-line bg-surface" />
      ))}
    </div>
  );
}
