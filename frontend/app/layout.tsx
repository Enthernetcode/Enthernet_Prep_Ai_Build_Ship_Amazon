import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "./lib/auth";

export const metadata: Metadata = {
  title: "Enthernet Prep AI",
  description: "Live in the Moment.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-eprep-bg font-sans text-eprep-text antialiased">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
