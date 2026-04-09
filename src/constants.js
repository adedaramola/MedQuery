export const API_BASE = process.env.REACT_APP_API_URL || "http://localhost:8000";

export const SOURCE_COLORS = {
  "Medical Q&A Collection": {
    bg: "rgba(16,185,129,0.12)",
    border: "#10b981",
    icon: "🩺",
    label: "Medical Q&A",
  },
  "Medical Device Manual": {
    bg: "rgba(99,102,241,0.12)",
    border: "#6366f1",
    icon: "🔬",
    label: "Device Manual",
  },
  "Web Search": {
    bg: "rgba(245,158,11,0.12)",
    border: "#f59e0b",
    icon: "🌐",
    label: "Web Search",
  },
  default: {
    bg: "rgba(100,116,139,0.12)",
    border: "#64748b",
    icon: "🔍",
    label: "Search",
  },
};

