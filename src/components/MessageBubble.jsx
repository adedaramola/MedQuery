import { SOURCE_COLORS } from "../constants";
import TypingIndicator from "./TypingIndicator";

function StreamingCursor() {
  return (
    <span
      style={{
        display: "inline-block",
        width: 2,
        height: "1em",
        background: "#6366f1",
        marginLeft: 2,
        verticalAlign: "text-bottom",
        animation: "blink 0.8s step-end infinite",
      }}
    />
  );
}

const BOT_AVATAR = (
  <div
    style={{
      width: 32,
      height: 32,
      borderRadius: "50%",
      background: "#f3f4f6",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      fontSize: 14,
      flexShrink: 0,
      border: "1px solid #e5e7eb",
    }}
  >
    🏥
  </div>
);

export default function MessageBubble({ msg }) {
  if (msg.role === "user") {
    return (
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 16 }}>
        <div
          style={{
            maxWidth: "72%",
            background: "linear-gradient(135deg,#6366f1,#8b5cf6)",
            color: "#fff",
            borderRadius: "18px 18px 4px 18px",
            padding: "12px 16px",
            fontSize: 14,
            lineHeight: 1.6,
            boxShadow: "0 4px 12px rgba(99,102,241,0.25)",
          }}
        >
          {msg.content}
        </div>
      </div>
    );
  }

  if (msg.loading) {
    return (
      <div style={{ display: "flex", gap: 10, marginBottom: 16, alignItems: "flex-start" }}>
        {BOT_AVATAR}
        <div style={{ background: "#f9fafb", border: "1px solid #e5e7eb", borderRadius: "18px 18px 18px 4px", overflow: "hidden" }}>
          <TypingIndicator />
        </div>
      </div>
    );
  }

  if (msg.error) {
    return (
      <div style={{ display: "flex", gap: 10, marginBottom: 16, alignItems: "flex-start" }}>
        <div
          style={{
            width: 32, height: 32, borderRadius: "50%",
            background: "#f3f4f6",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 14, flexShrink: 0, border: "1px solid #e5e7eb",
          }}
        >
          ⚠️
        </div>
        <div
          style={{
            maxWidth: "78%",
            background: "#7f1d1d",
            border: "1px solid #dc2626",
            borderRadius: "4px 18px 18px 18px",
            padding: "12px 16px",
            color: "#fca5a5",
            fontSize: 13,
            lineHeight: 1.6,
          }}
        >
          {msg.error}
        </div>
      </div>
    );
  }

  const src = SOURCE_COLORS[msg.source] || SOURCE_COLORS.default;
  const isRerouted = msg.relevance?.is_relevant === false;
  const isStreaming = msg.streaming === true;

  const tier = msg.source_quality?.tier;
  const tierColor =
    tier === "verified_corpus" ? "#10b981" :
    tier === "external_web"    ? "#f59e0b" : null;
  const tierBg =
    tier === "verified_corpus" ? "rgba(16,185,129,0.1)" :
    tier === "external_web"    ? "rgba(245,158,11,0.1)" : null;
  const tierLabel =
    tier === "verified_corpus" ? "✓ Verified corpus" :
    tier === "external_web"    ? "~ Web source" : null;

  return (
    <div style={{ display: "flex", gap: 10, marginBottom: 20, alignItems: "flex-start" }}>
      {BOT_AVATAR}
      <div style={{ maxWidth: "78%", display: "flex", flexDirection: "column", gap: 8 }}>
        {msg.source && (
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
            <span
              style={{
                background: src.bg, border: `1px solid ${src.border}`, color: src.border,
                borderRadius: 20, padding: "3px 10px", fontSize: 11, fontWeight: 600, letterSpacing: 0.5,
              }}
            >
              {src.icon} {src.label}
            </span>
            {msg.source_info?.reason && (
              <span
                style={{
                  background: "#f3f4f6", border: "1px solid #e5e7eb",
                  color: "#6b7280", borderRadius: 20, padding: "3px 10px", fontSize: 11,
                }}
              >
                {msg.source_info.reason}
              </span>
            )}
            {isRerouted && (
              <span
                style={{
                  background: "rgba(245,158,11,0.1)", border: "1px solid #f59e0b",
                  color: "#f59e0b", borderRadius: 20, padding: "3px 10px", fontSize: 11,
                }}
              >
                Re-routed to web
              </span>
            )}
            {tierLabel != null && !isStreaming && (
              <span
                style={{
                  background: tierBg, border: `1px solid ${tierColor}`,
                  color: tierColor, borderRadius: 20, padding: "3px 10px",
                  fontSize: 11, fontWeight: 600, letterSpacing: 0.3,
                }}
              >
                {tierLabel}
              </span>
            )}
          </div>
        )}

        <div
          style={{
            background: "#f9fafb", border: "1px solid #e5e7eb",
            borderRadius: "4px 18px 18px 18px", padding: "14px 16px",
            color: "#111827", fontSize: 14, lineHeight: 1.7,
            boxShadow: "0 1px 4px rgba(0,0,0,0.06)", minHeight: 48,
          }}
        >
          {msg.answer || msg.content || ""}
          {isStreaming && <StreamingCursor />}
        </div>

        {msg.timestamp && (
          <div style={{ fontSize: 11, color: "#9ca3af", display: "flex", gap: 12, marginTop: 4 }}>
            <span>{new Date(msg.timestamp).toLocaleTimeString()}</span>
            {msg.iteration_count > 0 && <span>Iterations: {msg.iteration_count}</span>}
          </div>
        )}
      </div>
    </div>
  );
}
