import "./globals.css";
import Nav from "@/components/Nav";

export const metadata = { title: { default: "Shelfmate", template: "%s · Shelfmate" } };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="font-sans">
        <Nav />
        <main className="mx-auto max-w-6xl space-y-8 px-4 py-9 md:px-10">{children}</main>
      </body>
    </html>
  );
}
