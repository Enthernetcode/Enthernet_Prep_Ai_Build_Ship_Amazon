import type { Metadata } from "next";
import Script from "next/script";
import "./globals.css";
import { AuthProvider } from "./lib/auth";
import { AnnouncementBanner } from "./components/AnnouncementBanner";

const SITE_URL = "https://eprep.enthernetservice.com";
const SITE_NAME = "Enthernet Prep AI";
const DESCRIPTION =
  "Enthernet Prep AI is an agentic readiness engine. Bring your CV, notes, " +
  "documents or pitch — Enthernet builds your competency map, challenges you " +
  "in realistic simulations, and measures readiness as you improve. Voice-native " +
  "via Alexa+ (Model Context Protocol) and the web.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: `${SITE_NAME} · Live in the Moment`,
    template: `%s · ${SITE_NAME}`,
  },
  description: DESCRIPTION,
  applicationName: SITE_NAME,
  authors: [{ name: "Enthernet" }],
  creator: "Enthernet",
  publisher: "Enthernet",
  keywords: [
    "Enthernet",
    "Enthernet Prep AI",
    "Prep AI",
    "interview preparation",
    "AI interview coach",
    "pitch practice",
    "readiness engine",
    "competency map",
    "adaptive learning",
    "mock interview",
    "job interview practice",
    "Alexa+",
    "Model Context Protocol",
    "MCP server",
    "agentic AI",
    "voice AI",
  ],
  category: "education",
  alternates: {
    canonical: SITE_URL,
  },
  openGraph: {
    type: "website",
    url: SITE_URL,
    siteName: SITE_NAME,
    title: `${SITE_NAME} · Live in the Moment`,
    description: DESCRIPTION,
    locale: "en_US",
    // Explicit absolute URL: `next dev` ignores metadataBase for file-based
    // metadata images and inserts localhost:3000, breaking social crawlers.
    images: [
      {
        url: `${SITE_URL}/opengraph-image.png`,
        width: 1200,
        height: 630,
        alt: `${SITE_NAME} — agentic readiness engine`,
        type: "image/png",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: `${SITE_NAME} · Live in the Moment`,
    description: DESCRIPTION,
    creator: "@enthernet",
    images: [`${SITE_URL}/twitter-image.png`],
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-snippet": -1,
      "max-image-preview": "large",
      "max-video-preview": -1,
    },
  },
  // Favicon + apple-touch icons are auto-picked up from app/icon.png and
  // app/apple-icon.png.
};

const JSON_LD = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      "@id": `${SITE_URL}/#organization`,
      name: "Enthernet",
      url: "https://enthernetservice.com/",
      sameAs: [
        "https://enthernetservice.com/",
        SITE_URL,
      ],
      description:
        "Enthernet builds agentic AI systems that turn preparation into a measurable, adaptive experience.",
    },
    {
      "@type": "SoftwareApplication",
      "@id": `${SITE_URL}/#app`,
      name: SITE_NAME,
      applicationCategory: "EducationalApplication",
      operatingSystem: "Web, Alexa+",
      url: SITE_URL,
      description: DESCRIPTION,
      offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
      publisher: { "@id": `${SITE_URL}/#organization` },
      featureList: [
        "Competency mapping from user documents",
        "Grounded adaptive interviewer",
        "Multi-dimensional evaluation rubric",
        "Deterministic readiness scoring",
        "Voice interface via Alexa+ (Model Context Protocol)",
        "Final Boss graded assessment",
      ],
    },
    {
      "@type": "WebSite",
      "@id": `${SITE_URL}/#website`,
      url: SITE_URL,
      name: SITE_NAME,
      description: DESCRIPTION,
      publisher: { "@id": `${SITE_URL}/#organization` },
      inLanguage: "en-US",
    },
  ],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <link rel="canonical" href={SITE_URL} />
        <meta name="theme-color" content="#0a0512" />
      </head>
      <body className="min-h-screen bg-eprep-bg font-sans text-eprep-text antialiased">
        <Script
          id="enthernet-jsonld"
          type="application/ld+json"
          strategy="beforeInteractive"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(JSON_LD) }}
        />
        <AuthProvider>
          <AnnouncementBanner />
          {children}
        </AuthProvider>
      </body>
    </html>
  );
}
