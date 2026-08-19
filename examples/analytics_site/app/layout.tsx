import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CFB Data Field Notes — Modular Analytics in Practice",
  description:
    "A local, source-backed demonstration of durable college football analytics recipes.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
