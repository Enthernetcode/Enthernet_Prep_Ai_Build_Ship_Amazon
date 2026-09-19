import { ImageResponse } from "next/og";

export const runtime = "edge";
export const alt = "Enthernet Prep AI — agentic readiness engine";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default async function OGImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "center",
          background:
            "radial-gradient(circle at 20% 20%, #7a2bff 0%, transparent 50%)," +
            "radial-gradient(circle at 80% 80%, #ff2bd6 0%, transparent 50%)," +
            "#0a0512",
          color: "#f5f0ff",
          fontFamily: "sans-serif",
          padding: 80,
        }}
      >
        <p
          style={{
            fontSize: 28,
            letterSpacing: 12,
            textTransform: "uppercase",
            color: "#a893c4",
            marginBottom: 24,
          }}
        >
          Enthernet
        </p>
        <p
          style={{
            fontSize: 160,
            fontWeight: 800,
            lineHeight: 1,
            margin: 0,
            background:
              "linear-gradient(90deg, #ff2bd6 0%, #7a2bff 50%, #2bb8ff 100%)",
            backgroundClip: "text",
            color: "transparent",
          }}
        >
          Prep AI
        </p>
        <p style={{ fontSize: 38, marginTop: 40, color: "#f5f0ff" }}>
          Live in the Moment.
        </p>
        <p
          style={{
            fontSize: 24,
            marginTop: 24,
            color: "#a893c4",
            textAlign: "center",
            maxWidth: 900,
          }}
        >
          Agentic readiness engine — competency map, adaptive simulations,
          voice-native via Alexa+ (MCP).
        </p>
      </div>
    ),
    size,
  );
}
