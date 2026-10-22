import Image from "next/image";

// Covers are small remote pictures. Skip Next's image optimizer and load them as they are.
export default function Cover({
  title,
  url,
  className,
}: {
  title: string;
  url: string | null;
  className: string;
}) {
  if (!url) {
    return (
      <div className={`flex items-end overflow-hidden bg-accent p-2 text-sm font-bold text-page ${className}`}>
        {title}
      </div>
    );
  }
  return (
    <Image src={url} alt={`Cover of ${title}`} width={200} height={300} unoptimized className={`object-cover ${className}`} />
  );
}
