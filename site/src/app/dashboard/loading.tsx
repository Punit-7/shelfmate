export default function Loading() {
  return (
    <div role="status" aria-label="Loading the dashboard" className="space-y-4">
      <div className="h-9 w-48 animate-pulse rounded bg-surface" />
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="h-24 animate-pulse rounded-2xl border border-line bg-surface" />
        ))}
      </div>
      <div className="h-64 animate-pulse rounded-2xl border border-line bg-surface" />
    </div>
  );
}
