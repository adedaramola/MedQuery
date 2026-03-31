export default function Header({ apiStatus }) {
  const statusColor =
    apiStatus === "healthy" ? "#10b981" :
    apiStatus === "unhealthy" ? "#f59e0b" : "#ef4444";

  return (
    <div
      style={{
        borderBottom: "1px solid #e5e7eb",
        padding: "14px 24px",
        display: "flex",
        alignItems: "center",
        gap: 12,
        background: "rgba(255,255,255,0.95)",
        backdropFilter: "blur(12px)",
        position: "sticky",
        top: 0,
        zIndex: 10,
      }}
    >
      <div
        style={{
          width: 36,
          height: 36,
          borderRadius: 10,
          background: "linear-gradient(135deg,#6366f1,#8b5cf6)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 18,
        }}
      >
        🏥
      </div>
      <div>
        <div
          style={{
            fontFamily: "'Space Grotesk',sans-serif",
            fontWeight: 700,
            fontSize: 16,
            color: "#111827",
            letterSpacing: -0.5,
          }}
        >
          MedQuery
        </div>
        <div style={{ fontSize: 11, color: "#9ca3af", letterSpacing: 0.5 }}>
          SEARCH · RETRIEVE · VERIFY · ANSWER
        </div>
      </div>
      <div style={{ marginLeft: "auto", display: "flex", gap: 12, alignItems: "center" }}>
        <div style={{ display: "flex", gap: 6 }}>
          {["QnA DB", "Device DB", "Web"].map((t, i) => (
            <div
              key={t}
              style={{
                padding: "4px 10px",
                borderRadius: 20,
                fontSize: 10,
                fontWeight: 600,
                letterSpacing: 0.8,
                border: `1px solid ${["#10b981", "#6366f1", "#f59e0b"][i]}`,
                color: ["#10b981", "#6366f1", "#f59e0b"][i],
                background: ["rgba(16,185,129,0.08)", "rgba(99,102,241,0.08)", "rgba(245,158,11,0.08)"][i],
              }}
            >
              {t}
            </div>
          ))}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 10, color: statusColor }}>
          <span
            className={`status-dot status-${apiStatus}`}
            style={{ animation: apiStatus !== "healthy" ? "pulse 1s infinite" : "none" }}
          />
          {apiStatus === "healthy" ? "Backend Ready" : apiStatus === "unhealthy" ? "Backend Issues" : "Disconnected"}
        </div>
      </div>
    </div>
  );
}
