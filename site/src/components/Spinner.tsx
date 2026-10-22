// A small spinning ring that takes the colour of the text around it.
export default function Spinner({ className = "" }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={`inline-block size-4 animate-spin rounded-full border-2 border-current border-t-transparent align-[-0.15em] ${className}`}
    />
  );
}
