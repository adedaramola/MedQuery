import { useState, useRef, useEffect } from "react";
import { API_BASE } from "./constants";
import Header from "./components/Header";
import MessageBubble from "./components/MessageBubble";

export default function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [apiStatus, setApiStatus] = useState("connecting");
  const bottomRef = useRef(null);
  const conversationId = useRef(crypto.randomUUID());

  useEffect(() => {
    checkApiHealth();
    const interval = setInterval(checkApiHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const checkApiHealth = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/health`);
      setApiStatus(res.ok ? "healthy" : "unhealthy");
    } catch {
      setApiStatus("disconnected");
    }
  };

  const sendMessage = async (text) => {
    const question = text || input.trim();
    if (!question || loading || apiStatus === "disconnected") return;

    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: question }, { role: "assistant", loading: true }]);
    setLoading(true);

    try {
      const response = await fetch(`${API_BASE}/api/query/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: question, conversation_id: conversationId.current }),
      });

      if (!response.ok) throw new Error(`API error: ${response.statusText}`);

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let assistantMsg = { role: "assistant", streaming: true };

      setMessages((prev) => [...prev.slice(0, -1), assistantMsg]);

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const raw = line.slice(6).trim();
          if (!raw) continue;

          let payload;
          try { payload = JSON.parse(raw); } catch { continue; }

          if (payload.type === "meta") {
            assistantMsg = { ...assistantMsg, source: payload.source, source_info: payload.source_info, relevance: payload.relevance, context: payload.context };
          } else if (payload.type === "token") {
            assistantMsg = { ...assistantMsg, answer: (assistantMsg.answer || "") + payload.token };
          } else if (payload.type === "done") {
            assistantMsg = { ...assistantMsg, streaming: false, answer: payload.answer, source_quality: payload.source_quality, iteration_count: payload.iteration_count, timestamp: payload.timestamp };
          } else if (payload.type === "error") {
            setMessages((prev) => [...prev.slice(0, -1), { role: "assistant", error: payload.message }]);
            return;
          }
          setMessages((prev) => [...prev.slice(0, -1), { ...assistantMsg }]);
        }
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev.slice(0, -1),
        { role: "assistant", error: `Failed to get response: ${err.message}. Check that the backend is running on ${API_BASE}` },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  };

  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column", background: "#ffffff", fontFamily: "'DM Mono', 'JetBrains Mono', monospace, 'Space Grotesk', sans-serif", color: "#111827" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&family=Space+Grotesk:wght@400;500;600;700&display=swap');
        * { box-sizing:border-box; margin:0; padding:0; }
        ::-webkit-scrollbar { width:4px; }
        ::-webkit-scrollbar-track { background:transparent; }
        ::-webkit-scrollbar-thumb { background:#d1d5db; border-radius:4px; }
        textarea:focus { outline:none; }
        textarea { resize:none; }
        @keyframes pulse { 0%,100%{opacity:0.3;transform:scale(0.8)} 50%{opacity:1;transform:scale(1)} }
        @keyframes fadeIn { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:translateY(0)} }
        @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }
        .msg-in { animation: fadeIn 0.3s ease; }
        .status-dot { width:8px; height:8px; border-radius:50%; display:inline-block; }
        .status-healthy { background:#10b981; }
        .status-unhealthy { background:#f59e0b; }
        .status-disconnected { background:#ef4444; }
      `}</style>

      <Header apiStatus={apiStatus} />

      <div style={{ flex: 1, overflowY: "auto", padding: "24px 20px", maxWidth: 800, width: "100%", margin: "0 auto" }}>
        {messages.length === 0 ? (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%" }}>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 48, marginBottom: 12 }}>🩺</div>
              <div style={{ fontFamily: "'Space Grotesk',sans-serif", fontSize: 22, fontWeight: 700, color: "#111827", marginBottom: 8 }}>
                MedQuery
              </div>
              <div style={{ color: "#6b7280", fontSize: 13, lineHeight: 1.8, maxWidth: 420, textAlign: "center" }}>
                Search across medical research, drug references, and clinical guidelines.
              </div>
            </div>
          </div>
        ) : (
          <div>
            {messages.map((m, i) => (
              <div key={i} className="msg-in"><MessageBubble msg={m} /></div>
            ))}
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div style={{ borderTop: "1px solid #e5e7eb", padding: "16px 20px", background: "rgba(255,255,255,0.95)", backdropFilter: "blur(12px)" }}>
        <div style={{ maxWidth: 800, margin: "0 auto", display: "flex", gap: 10, alignItems: "flex-end" }}>
          <div
            style={{ flex: 1, background: "#f9fafb", border: "1px solid #e5e7eb", borderRadius: 14, padding: "12px 16px", display: "flex", gap: 10, alignItems: "flex-end", transition: "border-color 0.2s" }}
            onFocus={(e) => (e.currentTarget.style.borderColor = "#6366f1")}
            onBlur={(e) => (e.currentTarget.style.borderColor = "#e5e7eb")}
          >
            <textarea value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={handleKey}
              placeholder="Ask about medical conditions or devices…"
              rows={1} disabled={apiStatus === "disconnected" || loading}
              style={{ flex: 1, background: "transparent", border: "none", color: "#111827", fontSize: 14, fontFamily: "inherit", lineHeight: 1.5, maxHeight: 120, overflowY: "auto", opacity: apiStatus === "disconnected" ? 0.5 : 1 }}
            />
          </div>
          <button onClick={() => sendMessage()} disabled={!input.trim() || loading || apiStatus === "disconnected"}
            style={{
              width: 44, height: 44, borderRadius: 12, fontSize: 18, flexShrink: 0,
              background: input.trim() && !loading && apiStatus !== "disconnected" ? "linear-gradient(135deg,#6366f1,#8b5cf6)" : "#f3f4f6",
              border: input.trim() && !loading && apiStatus !== "disconnected" ? "none" : "1px solid #e5e7eb",
              color: input.trim() && !loading && apiStatus !== "disconnected" ? "#fff" : "#9ca3af",
              cursor: input.trim() && !loading && apiStatus !== "disconnected" ? "pointer" : "default",
              transition: "all 0.2s", display: "flex", alignItems: "center", justifyContent: "center",
            }}>
            {loading ? "⟳" : "↑"}
          </button>
        </div>
        <div style={{ maxWidth: 800, margin: "6px auto 0", textAlign: "center", fontSize: 10, color: "#9ca3af", letterSpacing: 0.5 }}>
          ROUTES: QnA DB · Device Manual · Web Search · Relevance Check · Max 3 iterations
        </div>
      </div>
    </div>
  );
}
