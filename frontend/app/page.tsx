"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import { useAuth } from "./context/AuthContext";

// =====================================================================
// TypeScript Data Contracts
// =====================================================================

interface Citation {
  document: string;
  page: string | number;
  quoted_text: string;
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

interface EvaluateResponse {
  audit_id: string;
  org_id?: string;
  tx_hash: string;
  prev_hash: string;
  timestamp: string;
  risk_category: string;
  is_compliant: boolean;
  executive_summary_markdown: string;
  citations: Citation[];
  jurisdictions: string[];
  ledger_receipt?: {
    audit_id: string;
    org_id?: string;
    tx_hash: string;
    prev_hash: string;
    timestamp: string;
    status: string;
  };
}

interface OverrideResponse {
  audit_id: string;
  original_audit_id: string;
  org_id?: string;
  timestamp: string;
  model_provenance: string;
  prev_hash: string;
  tx_hash: string;
  status: string;
  justification: string;
}

interface LedgerBlock {
  audit_id: string;
  org_id?: string;
  timestamp: string;
  model_provenance: string;
  user_query: string;
  payload: Record<string, unknown>;
  prev_hash: string;
  tx_hash: string;
}

interface LedgerResponse {
  org_id?: string;
  total: number;
  chain_valid: boolean;
  total_blocks_verified: number;
  verification_error: string | null;
  blocks: LedgerBlock[];
}

const AVAILABLE_JURISDICTIONS = [
  { id: "EU (AI Act, GDPR, PSD2)", label: "EU Regulations", desc: "EU AI Act, GDPR, PSD2 RTS, MiCA, DORA" },
  { id: "UK (UK GDPR, Data Protection Act)", label: "UK Framework", desc: "Data Protection Act 2018, FCA AI Guidance" },
  { id: "US (CCPA/CPRA, SEC AI Guidance)", label: "US Framework", desc: "CCPA/CPRA, NIST AI RMF, SEC Guidance" },
];

const PRESET_QUERIES = [
  {
    title: "Biometric Payment Gateway",
    query: "We are developing a cloud-hosted biometric facial recognition gateway to categorize retail banking users and authorize high-value transactions automatically without human intervention.",
  },
  {
    title: "Crypto E-Money Token (MiCA)",
    query: "We are issuing an EMT token pegged to EUR with 100% reserve bank deposits held in ACPR-supervised French credit institutions and zero interest paid to token holders.",
  },
  {
    title: "Payment Initiation (PSD2 RTS)",
    query: "Implementing a PSD2 Payment Initiation Service (PIS) with dynamic linking for transaction amounts and Strong Customer Authentication (SCA) via Open Banking REST APIs.",
  },
  {
    title: "AI Credit Scoring (EU AI Act)",
    query: "Deploying a machine learning model that analyzes social media activity and utility payment histories to compute automated creditworthiness scores for loan applications.",
  },
];

export default function ComplianceDashboard() {
  const { user, token, isAuthenticated, isLoading: isAuthLoading, logout } = useAuth();
  const router = useRouter();

  // Input State
  const [query, setQuery] = useState("");
  const [selectedJurisdictions, setSelectedJurisdictions] = useState<string[]>([
    "EU (AI Act, GDPR, PSD2)",
  ]);

  // Conversational Memory & Evaluation Mode
  const [evalMode, setEvalMode] = useState<"strict" | "lenient">("strict");
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  // Execution & UI State
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [result, setResult] = useState<EvaluateResponse | null>(null);

  // Dispute & Override State
  const [justification, setJustification] = useState("");
  const [isOverriding, setIsOverriding] = useState(false);
  const [overrideResult, setOverrideResult] = useState<OverrideResponse | null>(null);
  const [overrideError, setOverrideError] = useState<string | null>(null);

  // Ledger Explorer State
  const [showLedgerModal, setShowLedgerModal] = useState(false);
  const [ledgerData, setLedgerData] = useState<LedgerResponse | null>(null);
  const [isLoadingLedger, setIsLoadingLedger] = useState(false);

  // Copy Feedback
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  // Authentication Guard
  useEffect(() => {
    if (!isAuthLoading && !isAuthenticated) {
      router.push("/login");
    }
  }, [isAuthenticated, isAuthLoading, router]);

  const copyToClipboard = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  const toggleJurisdiction = (id: string) => {
    if (selectedJurisdictions.includes(id)) {
      if (selectedJurisdictions.length > 1) {
        setSelectedJurisdictions(selectedJurisdictions.filter((j) => j !== id));
      }
    } else {
      setSelectedJurisdictions([...selectedJurisdictions, id]);
    }
  };

  // Helper: Format raw ISO timestamp to "Aug 22, 2026 • 00:03 AM"
  const formatTimestamp = (raw: string | undefined): string => {
    if (!raw) return "Recent";
    try {
      const d = new Date(raw);
      if (isNaN(d.getTime())) return raw;
      return new Intl.DateTimeFormat("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        hour12: true,
      }).format(d).replace(",", " •");
    } catch {
      return raw;
    }
  };

  // Helper: Truncate SHA-256 Hash to first 8 and last 8 characters
  const truncateHash = (hash: string | undefined): string => {
    if (!hash) return "N/A";
    if (hash.length <= 18) return hash;
    return `${hash.slice(0, 8)}...${hash.slice(-8)}`;
  };

  // Helper: Extract audit outcome badge from block payload
  const getBlockStatusPill = (block: LedgerBlock) => {
    const payload = (block.payload || {}) as Record<string, unknown>;
    const status = typeof payload.status === "string" ? payload.status : "";
    const provenance = block.model_provenance || "";
    const isOverridden = status === "OVERRIDDEN_BY_HUMAN" || provenance.includes("OVERRIDE");

    if (isOverridden) {
      return (
        <span className="inline-flex items-center space-x-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-amber-500/10 text-amber-300 border border-amber-500/20">
          <span className="h-1.5 w-1.5 rounded-full bg-amber-400"></span>
          <span>Human Override</span>
        </span>
      );
    }

    const risk = typeof payload.risk_category === "string" ? payload.risk_category : "";
    const isCompliant = payload.is_compliant === true;

    if (risk.toLowerCase().includes("pending")) {
      return (
        <span className="inline-flex items-center space-x-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-amber-500/10 text-amber-300 border border-amber-500/20">
          <span className="h-1.5 w-1.5 rounded-full bg-amber-400"></span>
          <span>Pending Clarification</span>
        </span>
      );
    }

    if (risk.toLowerCase().includes("prohibited") || risk.toLowerCase().includes("high")) {
      return (
        <span className="inline-flex items-center space-x-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-rose-500/10 text-rose-300 border border-rose-500/20">
          <span className="h-1.5 w-1.5 rounded-full bg-rose-400"></span>
          <span>{risk || "High-Risk"}</span>
        </span>
      );
    }

    if (isCompliant || risk.toLowerCase().includes("minimal")) {
      return (
        <span className="inline-flex items-center space-x-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400"></span>
          <span>{risk || "Compliant"}</span>
        </span>
      );
    }

    return (
      <span className="inline-flex items-center space-x-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-white/10 text-white/70 border border-white/10">
        <span className="h-1.5 w-1.5 rounded-full bg-white/50"></span>
        <span>{risk || "Audited"}</span>
      </span>
    );
  };

  // Submit Architecture for Streaming Evaluation
  const handleEvaluate = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!query.trim() || !token || isLoading) return;

    const currentQuery = query.trim();
    setIsLoading(true);
    setErrorMessage(null);
    setOverrideResult(null);
    setOverrideError(null);

    setResult({
      audit_id: "Computing...",
      tx_hash: "Streaming tokens...",
      prev_hash: "Linking previous block...",
      timestamp: new Date().toISOString(),
      risk_category: "Evaluating...",
      is_compliant: true,
      executive_summary_markdown: "",
      citations: [],
      jurisdictions: selectedJurisdictions,
    });

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      
      // Prepare multi-turn conversation history (excluding the prompt currently being sent)
      const currentHistory = messages.map((m) => ({
        role: m.role,
        content: m.content,
      }));

      const res = await fetch(`${apiUrl}/api/v1/evaluate`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          query: currentQuery,
          jurisdictions: selectedJurisdictions,
          history: currentHistory,
          mode: evalMode,
        }),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || `Server returned HTTP ${res.status}`);
      }

      if (!res.body) {
        throw new Error("Response body is not readable for SSE streaming.");
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let streamBuffer = "";
      let accumulatedSummary = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        streamBuffer += decoder.decode(value, { stream: true });
        const lines = streamBuffer.split("\n\n");
        streamBuffer = lines.pop() || "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith("data:")) {
            try {
              const payload = JSON.parse(trimmed.replace(/^data:\s*/, ""));

              if (payload.type === "start") {
                setResult((prev) => ({
                  audit_id: prev?.audit_id || "Computing...",
                  tx_hash: prev?.tx_hash || "Streaming tokens...",
                  prev_hash: prev?.prev_hash || "...",
                  timestamp: prev?.timestamp || new Date().toISOString(),
                  risk_category: prev?.risk_category || "Evaluating...",
                  is_compliant: prev?.is_compliant ?? true,
                  executive_summary_markdown: prev?.executive_summary_markdown || "",
                  citations: payload.citations || [],
                  jurisdictions: payload.jurisdictions || selectedJurisdictions,
                }));
              } else if (payload.type === "token") {
                const tokenString =
                  typeof payload.content === "string"
                    ? payload.content
                    : Array.isArray(payload.content)
                    ? payload.content
                        .map((c: unknown) =>
                          typeof c === "string"
                            ? c
                            : (c as { text?: string; content?: string })?.text ||
                              (c as { text?: string; content?: string })?.content ||
                              ""
                        )
                        .join("")
                    : (payload.content?.text || payload.content?.content || "");

                if (tokenString) {
                  accumulatedSummary += tokenString;
                  setResult((prev) => {
                    if (!prev) return prev;
                    return {
                      ...prev,
                      executive_summary_markdown:
                        (prev.executive_summary_markdown || "") + tokenString,
                    };
                  });
                }
              } else if (payload.type === "done") {
                const finalSummary = payload.executive_summary_markdown || accumulatedSummary;
                setResult({
                  audit_id: payload.audit_id || "LOCAL_COMMITTED",
                  tx_hash: payload.tx_hash || "NO_TX_HASH",
                  prev_hash: payload.prev_hash || "0".repeat(64),
                  timestamp: payload.timestamp || new Date().toISOString(),
                  risk_category: payload.risk_category || "Minimal Risk",
                  is_compliant: payload.is_compliant ?? true,
                  citations: payload.citations || [],
                  jurisdictions: payload.jurisdictions || selectedJurisdictions,
                  executive_summary_markdown: finalSummary,
                });

                // Commit turn to multi-turn conversation history
                setMessages((prev) => [
                  ...prev,
                  { role: "user", content: currentQuery },
                  { role: "assistant", content: finalSummary },
                ]);
              } else if (payload.type === "error") {
                setErrorMessage(payload.detail || "An error occurred during evaluation.");
              }
            } catch {
              // Ignore partial JSON chunks
            }
          }
        }
      }
    } catch (err: unknown) {
      const message =
        err instanceof Error
          ? err.message
          : "Failed to connect to FastAPI backend service.";
      setErrorMessage(message);
    } finally {
      setIsLoading(false);
    }
  };

  // Reset Conversational Thread
  const handleResetConversation = () => {
    setMessages([]);
    setResult(null);
    setErrorMessage(null);
    setQuery("");
  };

  // Submit Human Override
  const handleOverride = async () => {
    if (!result?.audit_id || !justification.trim() || !token || isOverriding) return;

    setIsOverriding(true);
    setOverrideError(null);

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const res = await fetch(`${apiUrl}/api/v1/override`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          audit_id: result.audit_id,
          justification: justification.trim(),
        }),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || `Override submission failed (${res.status})`);
      }

      const data: OverrideResponse = await res.json();
      setOverrideResult(data);
      setJustification("");
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to record dispute override.";
      setOverrideError(message);
    } finally {
      setIsOverriding(false);
    }
  };

  // Fetch Recent Ledger Blocks
  const fetchLedgerHistory = async () => {
    if (!token) return;
    setIsLoadingLedger(true);
    setShowLedgerModal(true);
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const res = await fetch(`${apiUrl}/api/v1/ledger?limit=10`, {
        credentials: "include",
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      if (res.ok) {
        const data: LedgerResponse = await res.json();
        setLedgerData(data);
      }
    } catch {
      // ignore
    } finally {
      setIsLoadingLedger(false);
    }
  };

  // Admin Check
  const isAdmin =
    user?.role === "MASTER_ADMIN" ||
    user?.role?.toUpperCase() === "ADMIN" ||
    user?.role?.toUpperCase() === "SUPER_ADMIN";

  // Prompt / Audit Record Hard Delete (Admin Only)
  const handleDeletePrompt = async (auditId: string) => {
    const confirmed = window.confirm(
      "Are you sure you want to delete this prompt / audit record? This action cannot be undone."
    );
    if (!confirmed) return;

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const headers: Record<string, string> = {};
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }

      const res = await fetch(`${apiUrl}/api/v1/prompts/${auditId}`, {
        method: "DELETE",
        credentials: "include",
        headers,
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || `Server returned HTTP ${res.status}`);
      }

      if (ledgerData) {
        setLedgerData({
          ...ledgerData,
          blocks: ledgerData.blocks.filter((b) => b.audit_id !== auditId),
          total: Math.max(0, ledgerData.total - 1),
        });
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to delete prompt.";
      alert(msg);
    }
  };

  if (isAuthLoading || !isAuthenticated) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center text-white/50 font-light text-sm">
        Verifying cryptographic session credentials...
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-slate-900 via-[#150e28] to-slate-950 text-white/90 relative overflow-x-hidden selection:bg-indigo-500/30 selection:text-white flex flex-col font-sans">
      {/* Ambient Glassmorphism Gradient Glow Orbs */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden z-0">
        <div className="absolute -top-48 -right-48 w-[700px] h-[700px] bg-purple-600/15 rounded-full blur-[150px] animate-pulse" />
        <div className="absolute top-1/2 -left-48 w-[600px] h-[600px] bg-indigo-600/15 rounded-full blur-[140px]" />
        <div className="absolute -bottom-48 right-1/3 w-[650px] h-[650px] bg-sky-600/10 rounded-full blur-[160px]" />
      </div>

      {/* Frosted Glass Navigation Bar */}
      <header className="border-b border-white/10 bg-white/[0.02] backdrop-blur-2xl sticky top-0 z-40 transition-all duration-200">
        <div className="max-w-6xl mx-auto px-6 sm:px-8 h-20 flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <div className="h-11 w-11 rounded-2xl bg-white/[0.08] border border-white/15 p-0.5 flex items-center justify-center shadow-[0_8px_32px_0_rgba(0,0,0,0.37)] backdrop-blur-xl">
              <span className="text-xl">⚖️</span>
            </div>
            <div>
              <div className="flex items-center space-x-2.5">
                <span className="font-semibold text-lg tracking-tight text-white/95">
                  FinSight
                </span>
                <span className="text-[11px] px-2.5 py-0.5 rounded-full bg-white/10 text-white/80 border border-white/15 font-mono">
                  {user?.org_name || "Enterprise Tenant"}
                </span>
              </div>
              <p className="text-xs text-white/50 font-light hidden sm:block">
                AI Compliance Gatekeeper & Immutable Cryptographic Ledger
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-3">
            {/* User & Role Badge */}
            <div className="hidden md:flex items-center space-x-2">
              <span className="text-xs text-white/60 font-light">{user?.email}</span>
              {user?.role === "MASTER_ADMIN" && (
                <span className="px-2.5 py-0.5 rounded-full bg-purple-500/15 text-purple-300 border border-purple-500/25 text-[11px] font-mono">
                  MASTER_ADMIN
                </span>
              )}
              {user?.role === "MANAGER" && (
                <span className="px-2.5 py-0.5 rounded-full bg-sky-500/15 text-sky-300 border border-sky-500/25 text-[11px] font-mono">
                  MANAGER
                </span>
              )}
              {user?.role === "DEVELOPER" && (
                <span className="px-2.5 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/25 text-[11px] font-mono">
                  DEVELOPER
                </span>
              )}
            </div>

            {/* Live Simulator Link */}
            <Link
              href="/simulator"
              className="text-xs px-3.5 py-2 rounded-xl bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-200 border border-indigo-500/25 backdrop-blur-xl transition-all duration-200 ease-out flex items-center space-x-1.5 shadow-[0_4px_20px_0_rgba(99,102,241,0.15)] active:scale-95 group"
              title="Automated Transaction Gatekeeper Simulator"
            >
              <span className="text-indigo-400 group-hover:scale-110 transition-transform">⚡</span>
              <span className="font-medium">Live Simulator</span>
            </Link>

            {/* Admin Team Mgmt Link */}
            {user?.role === "MASTER_ADMIN" && (
              <Link
                href="/admin"
                className="text-xs px-3.5 py-2 rounded-xl bg-purple-500/10 hover:bg-purple-500/20 text-purple-200 border border-purple-500/20 backdrop-blur-xl transition-all duration-200 ease-out flex items-center space-x-1.5 shadow-[0_4px_20px_0_rgba(0,0,0,0.2)] active:scale-95"
              >
                <span>👥</span>
                <span className="font-medium">Team Mgmt</span>
              </Link>
            )}

            <button
              onClick={fetchLedgerHistory}
              className="text-xs px-4 py-2 rounded-xl bg-white/[0.06] hover:bg-white/[0.12] text-white/80 hover:text-white border border-white/15 backdrop-blur-xl transition-all duration-200 ease-out flex items-center space-x-2 shadow-[0_4px_20px_0_rgba(0,0,0,0.2)] active:scale-95"
            >
              <span>⛓️</span>
              <span className="font-medium">Ledger Explorer</span>
            </button>

            <button
              onClick={logout}
              className="text-xs px-3.5 py-2 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/20 backdrop-blur-xl transition-all duration-200 ease-out active:scale-95"
            >
              Sign Out
            </button>
          </div>
        </div>
      </header>

      {/* Main Flowing Canvas */}
      <main className="max-w-5xl mx-auto px-6 sm:px-8 py-14 flex-1 w-full space-y-14 relative z-10">
        {/* Hero Banner */}
        <section className="text-center space-y-5 max-w-3xl mx-auto">
          <div className="inline-flex items-center space-x-2 px-3.5 py-1.5 rounded-full bg-white/5 border border-white/10 text-xs text-white/70 backdrop-blur-xl shadow-inner">
            <span>⚡</span>
            <span>Real-Time Multi-Turn Agentic Compliance Auditor</span>
          </div>
          <h1 className="text-4xl sm:text-5xl font-light tracking-tight text-white/95 leading-tight">
            Cross-examine Fintech Architecture <br className="hidden sm:inline" />
            Against 8 EU Regulatory Frameworks.
          </h1>
          <p className="text-sm sm:text-base text-white/60 font-light max-w-2xl mx-auto leading-relaxed">
            Streaming evaluation against AMLD6/5, PSD2, MiCA, TFR, DORA, EU AI Act, and GDPR with full multi-turn conversational memory.
          </p>

          <div className="flex flex-wrap items-center justify-center gap-3 pt-2">
            <a
              href="#architectural-evaluator"
              className="px-6 py-3.5 rounded-2xl bg-white hover:bg-white/90 text-slate-950 font-medium text-xs sm:text-sm transition-all duration-200 ease-out flex items-center space-x-2 shadow-[0_4px_20px_0_rgba(255,255,255,0.2)] active:scale-95"
            >
              <span>🏛️</span>
              <span>Evaluate Architecture</span>
              <span>&darr;</span>
            </a>
            <Link
              href="/simulator"
              className="px-6 py-3.5 rounded-2xl bg-white/[0.06] hover:bg-white/[0.12] text-white border border-white/15 backdrop-blur-xl transition-all duration-200 ease-out flex items-center space-x-2 shadow-[0_4px_20px_0_rgba(0,0,0,0.2)] active:scale-95 hover:border-indigo-500/40 group"
            >
              <span className="text-indigo-400 group-hover:scale-110 transition-transform">⚡</span>
              <span className="font-medium text-xs sm:text-sm">Test Transaction API ⚡</span>
            </Link>
          </div>
        </section>

        {/* Multi-Turn Conversation Thread (If Present) */}
        {messages.length > 0 && (
          <section className="bg-white/5 backdrop-blur-2xl border border-white/10 shadow-[0_8px_32px_0_rgba(0,0,0,0.37)] rounded-[2.5rem] p-6 sm:p-8 space-y-4">
            <div className="flex items-center justify-between border-b border-white/10 pb-3">
              <div className="flex items-center space-x-2.5">
                <span className="text-lg">💬</span>
                <h3 className="text-base font-light text-white/95">Conversational Audit Thread ({messages.length / 2} Turns)</h3>
              </div>
              <button
                onClick={handleResetConversation}
                className="px-3 py-1.5 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/20 text-xs font-medium transition-all active:scale-95 flex items-center space-x-1.5"
              >
                <span>🔄</span>
                <span>Reset Conversation Thread</span>
              </button>
            </div>
            <div className="space-y-3 max-h-60 overflow-y-auto pr-2">
              {messages.map((msg, idx) => (
                <div
                  key={idx}
                  className={`p-3.5 rounded-2xl text-xs leading-relaxed ${
                    msg.role === "user"
                      ? "bg-indigo-500/10 border border-indigo-500/20 text-indigo-200 ml-6"
                      : "bg-white/[0.03] border border-white/5 text-white/80 mr-6"
                  }`}
                >
                  <span className="font-semibold block mb-1 font-mono text-[10px] uppercase text-white/40">
                    {msg.role === "user" ? "👤 Architect Submission" : "⚖️ FinSight Auditor Response"}
                  </span>
                  <p className="line-clamp-2">{msg.content}</p>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Section A: The Architectural Input & Mode Selection */}
        <section id="architectural-evaluator" className="bg-white/5 backdrop-blur-2xl border border-white/10 shadow-[0_8px_32px_0_rgba(0,0,0,0.37)] rounded-[2.5rem] p-8 sm:p-12 space-y-8 relative overflow-hidden transition-all duration-200 scroll-mt-28">

          <div className="space-y-2">
            <h2 className="text-2xl sm:text-3xl font-light text-white/95 tracking-tight flex items-center space-x-3">
              <span>🏛️</span>
              <span>Architectural Specification</span>
            </h2>
            <p className="text-sm text-white/60 font-light leading-relaxed">
              Describe your proposed data flows, licensing models, ICT topology, or transaction infrastructure for high-speed streaming compliance analysis.
            </p>
          </div>

          {/* 1. Evaluation Mode Toggle */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 rounded-3xl bg-black/30 border border-white/10 backdrop-blur-md">
            <div className="space-y-1">
              <div className="flex items-center space-x-2">
                <span className="text-sm font-medium text-white/95">Auditor Evaluation Mode</span>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-white/10 text-white/70 font-mono">
                  {evalMode === "strict" ? "3-State Matrix" : "Scope-Limited"}
                </span>
              </div>
              <p className="text-xs text-white/50 font-light">
                {evalMode === "strict"
                  ? "Enforces strict 3-state agentic auditing across all 8 EU acts with 'Pending Clarification' routing."
                  : "Scope-limited demo mode evaluating only explicitly stated mechanisms without administrative penalties."}
              </p>
            </div>

            <div className="inline-flex p-1 rounded-2xl bg-black/60 border border-white/10 self-start sm:self-auto">
              <button
                type="button"
                onClick={() => setEvalMode("strict")}
                className={`px-4 py-2 rounded-xl text-xs font-medium transition-all duration-200 flex items-center space-x-2 ${
                  evalMode === "strict"
                    ? "bg-indigo-600 text-white shadow-[0_0_20px_0_rgba(99,102,241,0.4)]"
                    : "text-white/50 hover:text-white"
                }`}
              >
                <span>🛡️</span>
                <span>Auditor (Strict)</span>
              </button>
              <button
                type="button"
                onClick={() => setEvalMode("lenient")}
                className={`px-4 py-2 rounded-xl text-xs font-medium transition-all duration-200 flex items-center space-x-2 ${
                  evalMode === "lenient"
                    ? "bg-purple-600 text-white shadow-[0_0_20px_0_rgba(168,85,247,0.4)]"
                    : "text-white/50 hover:text-white"
                }`}
              >
                <span>⚡</span>
                <span>Demo (Lenient)</span>
              </button>
            </div>
          </div>

          {/* Quick Preset Queries */}
          <div className="space-y-3">
            <div className="text-xs uppercase tracking-wider text-white/40 font-medium font-mono">
              Demo Architectural Templates:
            </div>
            <div className="flex flex-wrap gap-2.5">
              {PRESET_QUERIES.map((preset, idx) => (
                <button
                  key={idx}
                  onClick={() => setQuery(preset.query)}
                  className="text-xs px-4 py-2.5 rounded-2xl bg-white/[0.04] hover:bg-white/[0.10] border border-white/10 hover:border-white/20 text-white/80 hover:text-white transition-all duration-200 ease-out text-left backdrop-blur-md active:scale-95 shadow-sm"
                >
                  <span className="text-indigo-400 font-mono mr-1.5 font-bold">[{idx + 1}]</span>
                  {preset.title}
                </button>
              ))}
            </div>
          </div>

          <form onSubmit={handleEvaluate} className="space-y-6">
            <div className="relative">
              <textarea
                rows={5}
                required
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="e.g., We are issuing an EUR-referenced e-money token under MiCA with 100% reserve assets held in separate French banking accounts..."
                className="w-full bg-black/30 border border-white/10 rounded-3xl p-6 text-sm sm:text-base text-white/90 placeholder-white/30 focus:outline-none focus:border-white/40 focus:ring-1 focus:ring-white/30 backdrop-blur-md transition-all duration-200 ease-out resize-y leading-relaxed font-light shadow-inner"
              />
            </div>

            {/* Jurisdiction Multi-Select Pills */}
            <div className="space-y-3">
              <div className="text-xs uppercase tracking-wider text-white/40 font-medium font-mono">
                Target Legal Frameworks:
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {AVAILABLE_JURISDICTIONS.map((j) => {
                  const isSelected = selectedJurisdictions.includes(j.id);
                  return (
                    <button
                      type="button"
                      key={j.id}
                      onClick={() => toggleJurisdiction(j.id)}
                      className={`p-4 rounded-2xl border text-left transition-all duration-200 ease-out backdrop-blur-md flex flex-col justify-between active:scale-95 ${
                        isSelected
                          ? "bg-indigo-500/15 border-indigo-500/40 text-white shadow-[0_0_20px_0_rgba(99,102,241,0.15)]"
                          : "bg-white/[0.02] border-white/5 text-white/50 hover:border-white/15 hover:text-white/80"
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm font-medium">{j.label}</span>
                        <span className="text-xs">{isSelected ? "✓" : "+"}</span>
                      </div>
                      <span className="text-[11px] opacity-70 font-light">{j.desc}</span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Submit Action */}
            <div className="pt-2 flex items-center justify-between">
              <button
                type="submit"
                disabled={isLoading || !query.trim()}
                className="w-full sm:w-auto px-8 py-4 rounded-2xl bg-white hover:bg-white/90 text-slate-950 font-medium text-sm transition-all duration-200 ease-out disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center space-x-3 shadow-[0_4px_20px_0_rgba(255,255,255,0.2)] active:scale-95"
              >
                {isLoading ? (
                  <>
                    <span className="inline-block animate-spin">⏳</span>
                    <span>Streaming 3-State Agentic Audit...</span>
                  </>
                ) : (
                  <>
                    <span>⚡</span>
                    <span>Run Streaming Compliance Evaluation</span>
                  </>
                )}
              </button>
            </div>
          </form>

          {errorMessage && (
            <div className="p-4 rounded-2xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs flex items-center space-x-3 animate-in fade-in duration-200">
              <span>⚠️</span>
              <span>{errorMessage}</span>
            </div>
          )}
        </section>

        {/* Section B: The Compliance Evaluation Results Canvas */}
        {result && (
          <div className="space-y-12 animate-in fade-in duration-300">
            {/* 1. 3-State Compliance Badge UI */}
            <section className="bg-white/5 backdrop-blur-2xl border border-white/10 shadow-[0_8px_32px_0_rgba(0,0,0,0.37)] rounded-[2.5rem] p-8 sm:p-12 flex flex-col sm:flex-row sm:items-center justify-between gap-6 relative overflow-hidden">
              <div className="space-y-2">
                <div className="text-xs uppercase tracking-wider text-white/40 font-mono">
                  Primary Audit Determination
                </div>
                <div className="flex items-center space-x-4">
                  {/* State 1: Fully Compliant */}
                  {result.is_compliant ? (
                    <div className="flex items-center space-x-3">
                      <span className="text-3xl sm:text-4xl">🟢</span>
                      <div>
                        <h2 className="text-3xl sm:text-4xl font-light text-emerald-400 tracking-tight">
                          Compliant Architecture
                        </h2>
                        <p className="text-xs text-white/50 font-light mt-1">
                          All applicable European statutory requirements verified and satisfied.
                        </p>
                      </div>
                    </div>
                  ) : result.risk_category === "Pending Clarification" ||
                    result.executive_summary_markdown.toLowerCase().includes("pending clarification") ||
                    result.executive_summary_markdown.toLowerCase().includes("pending information") ? (
                    /* State 2: Pending Clarification (Inquiries Required) */
                    <div className="flex items-center space-x-3">
                      <span className="text-3xl sm:text-4xl">⏳</span>
                      <div>
                        <h2 className="text-3xl sm:text-4xl font-light text-amber-400 tracking-tight">
                          Pending Clarification
                        </h2>
                        <p className="text-xs text-white/50 font-light mt-1">
                          Compliance determination suspended pending required architectural and operational details.
                        </p>
                      </div>
                    </div>
                  ) : (
                    /* State 3: Active Legal Violation / High-Risk */
                    <div className="flex items-center space-x-3">
                      <span className="text-3xl sm:text-4xl">🔴</span>
                      <div>
                        <h2 className="text-3xl sm:text-4xl font-light text-rose-400 tracking-tight">
                          Action Required / High-Risk
                        </h2>
                        <p className="text-xs text-white/50 font-light mt-1">
                          Classified under {result.risk_category} risk tier with active legal breaches or high-risk obligations.
                        </p>
                      </div>
                    </div>
                  )}
                </div>
              </div>

              <div className="px-6 py-3 rounded-full bg-indigo-500/[0.08] border border-indigo-500/20 text-indigo-200 backdrop-blur-xl flex items-center space-x-2 shadow-[0_4px_20px_0_rgba(0,0,0,0.2)]">
                <span>🔒</span>
                <span className="text-xs font-semibold uppercase tracking-wider">
                  {result.tx_hash === "Streaming tokens..." ? "Awaiting Token Seal" : "SHA-256 Ledger Sealed"}
                </span>
              </div>
            </section>

            {/* 2. Cryptographic Compliance Receipt Bar */}
            <section className="bg-white/5 backdrop-blur-2xl border border-white/10 shadow-[0_8px_32px_0_rgba(0,0,0,0.37)] rounded-3xl p-6 sm:p-8 space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2.5">
                  <span className="text-lg">🛡️</span>
                  <h3 className="text-base font-light text-white/95">Cryptographic Compliance Receipt</h3>
                </div>
                <span className="text-[11px] px-3 py-1 bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 rounded-full font-mono">
                  {result.tx_hash === "Streaming tokens..." ? "STREAMING" : "POSTGRESQL IMMUTABLE"}
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs font-mono">
                {/* Audit ID */}
                <div className="bg-black/30 p-3.5 rounded-2xl border border-white/5 flex items-center justify-between backdrop-blur-md">
                  <div className="truncate mr-2">
                    <span className="text-white/40 block text-[10px] uppercase font-sans font-medium">Audit UUID</span>
                    <span className="text-white/90 text-xs font-mono">{result.audit_id}</span>
                  </div>
                  <button
                    onClick={() => copyToClipboard(result.audit_id, "audit_id")}
                    className="px-2.5 py-1 bg-white/10 hover:bg-white/20 text-white/80 rounded-lg text-[10px] font-sans border border-white/10 transition-all duration-200 ease-out active:scale-95"
                  >
                    {copiedKey === "audit_id" ? "Copied!" : "Copy"}
                  </button>
                </div>

                {/* Tx Hash */}
                <div className="bg-black/30 p-3.5 rounded-2xl border border-white/5 flex items-center justify-between backdrop-blur-md">
                  <div className="truncate mr-2">
                    <span className="text-indigo-300/80 block text-[10px] uppercase font-sans font-medium">Block Tx Hash</span>
                    <span className="text-indigo-200 text-xs font-mono">{result.tx_hash}</span>
                  </div>
                  <button
                    onClick={() => copyToClipboard(result.tx_hash, "tx_hash")}
                    className="px-2.5 py-1 bg-white/10 hover:bg-white/20 text-white/80 rounded-lg text-[10px] font-sans border border-white/10 transition-all duration-200 ease-out active:scale-95"
                  >
                    {copiedKey === "tx_hash" ? "Copied!" : "Copy"}
                  </button>
                </div>

                {/* Previous Hash */}
                <div className="bg-black/30 p-3.5 rounded-2xl border border-white/5 flex items-center justify-between backdrop-blur-md">
                  <div className="truncate mr-2">
                    <span className="text-white/40 block text-[10px] uppercase font-sans font-medium">Previous Linked Hash</span>
                    <span className="text-white/60 text-xs font-mono">{result.prev_hash}</span>
                  </div>
                  <button
                    onClick={() => copyToClipboard(result.prev_hash, "prev_hash")}
                    className="px-2.5 py-1 bg-white/10 hover:bg-white/20 text-white/80 rounded-lg text-[10px] font-sans border border-white/10 transition-all duration-200 ease-out active:scale-95"
                  >
                    {copiedKey === "prev_hash" ? "Copied!" : "Copy"}
                  </button>
                </div>
              </div>
            </section>

            {/* 3. Executive Legal Analysis (Streaming ReactMarkdown Canvas) */}
            <section className="bg-white/5 backdrop-blur-2xl border border-white/10 shadow-[0_8px_32px_0_rgba(0,0,0,0.37)] rounded-[2.5rem] p-8 sm:p-12 space-y-6">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <span className="text-2xl">📋</span>
                  <h3 className="text-2xl sm:text-3xl font-light text-white/95 tracking-tight">
                    Executive Legal Analysis
                  </h3>
                </div>
                {isLoading && (
                  <div className="flex items-center space-x-2 text-xs text-indigo-300 bg-indigo-500/10 px-3 py-1 rounded-full border border-indigo-500/20 animate-pulse">
                    <span className="h-2 w-2 rounded-full bg-indigo-400"></span>
                    <span>Streaming Tokens in Real-Time...</span>
                  </div>
                )}
              </div>

              <div className="bg-black/30 p-8 sm:p-10 rounded-3xl border border-white/5 backdrop-blur-md prose prose-invert max-w-none prose-p:text-lg prose-p:leading-relaxed prose-headings:font-light prose-headings:text-white/95 prose-strong:text-white prose-a:text-blue-400 prose-ul:text-lg prose-li:text-lg font-light text-white/80 space-y-4">
                <ReactMarkdown>
                  {result.executive_summary_markdown || "Awaiting tokens from Flash RAG stream..."}
                </ReactMarkdown>
              </div>
            </section>

            {/* 4. Collapsible Legal Citations Accordions */}
            <section className="bg-white/5 backdrop-blur-2xl border border-white/10 shadow-[0_8px_32px_0_rgba(0,0,0,0.37)] rounded-[2.5rem] p-8 sm:p-12 space-y-6">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <span className="text-2xl">📚</span>
                  <h3 className="text-2xl sm:text-3xl font-light text-white/95 tracking-tight">
                    Verified Statutory Citations
                  </h3>
                </div>
                <span className="text-xs px-3 py-1 rounded-full bg-white/10 text-white/70 border border-white/10 font-mono">
                  {result.citations?.length || 0} Grounded References
                </span>
              </div>

              {result.citations && result.citations.length > 0 ? (
                <div className="space-y-3">
                  {result.citations.map((cit, idx) => (
                    <details
                      key={idx}
                      className="group bg-black/30 rounded-2xl border border-white/10 overflow-hidden backdrop-blur-md transition-all duration-200 open:border-indigo-500/30 open:bg-black/40 shadow-sm"
                    >
                      <summary className="px-6 py-4 cursor-pointer font-semibold text-indigo-300 hover:text-indigo-200 flex items-center justify-between transition-colors list-none select-none">
                        <div className="flex flex-wrap items-center gap-2.5">
                          <span className="text-xs px-2.5 py-0.5 rounded-full bg-indigo-500/15 border border-indigo-500/25 text-indigo-300 font-mono">
                            Citation #{idx + 1}
                          </span>
                          <span className="text-sm text-white/90">
                            {cit.document}
                          </span>
                          <span className="text-xs text-white/50 font-mono font-normal">
                            • {String(cit.page).startsWith("Article") ? cit.page : `Page / Article: ${cit.page || "N/A"}`}
                          </span>
                        </div>
                        <span className="text-xs text-white/40 group-open:rotate-180 transition-transform duration-200 ml-2">
                          ▼
                        </span>
                      </summary>
                      <div className="px-6 pb-5 pt-1 text-sm text-white/80">
                        <blockquote className="mt-2 pl-4 border-l-4 border-indigo-500/40 text-sm text-white/80 whitespace-pre-wrap italic bg-white/[0.02] p-4 rounded-r-xl leading-relaxed font-light">
                          &ldquo;{cit.quoted_text || "No quote extracted."}&rdquo;
                        </blockquote>
                      </div>
                    </details>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-white/40 italic">
                  {isLoading
                    ? "Retrieving grounded citation snippets from FAISS..."
                    : "No specific citation references extracted for this query."}
                </p>
              )}
            </section>

            {/* 5. Human-in-the-Loop Dispute & Override Section - Restricted for DEVELOPER Role */}
            {user?.role !== "DEVELOPER" && (
              <section className="bg-white/5 backdrop-blur-2xl border border-white/10 shadow-[0_8px_32px_0_rgba(0,0,0,0.37)] rounded-[2.5rem] p-8 sm:p-12 space-y-6">
                <div className="space-y-1.5">
                  <h3 className="text-xl sm:text-2xl font-light text-amber-300 flex items-center space-x-3">
                    <span>⚖️</span>
                    <span>Human-in-the-Loop Ledger Dispute Protocol</span>
                  </h3>
                  <p className="text-sm text-white/60 font-light leading-relaxed">
                    Dispute this AI compliance determination by appending an immutable human override block to the PostgreSQL ledger without breaking SHA-256 chain continuity.
                  </p>
                </div>

                {overrideResult ? (
                  <div className="p-6 rounded-3xl bg-amber-500/[0.08] border border-amber-500/25 space-y-3 text-sm backdrop-blur-md animate-in fade-in duration-200">
                    <div className="font-medium text-amber-300 flex items-center space-x-2 text-base">
                      <span>✅</span>
                      <span>Dispute Override Permanently Committed to Cryptographic Ledger!</span>
                    </div>
                    <div className="font-mono text-xs text-white/80 bg-black/40 p-4 rounded-2xl border border-white/5 space-y-2">
                      <div>
                        <span className="text-white/40">New Block Tx Hash: </span>
                        <span className="text-amber-200">{overrideResult.tx_hash}</span>
                      </div>
                      <div>
                        <span className="text-white/40">Linked Previous Hash: </span>
                        <span className="text-white/60">{overrideResult.prev_hash}</span>
                      </div>
                      <div>
                        <span className="text-white/40">Status: </span>
                        <span className="text-amber-300 font-bold">{overrideResult.status}</span>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-4">
                    <textarea
                      rows={3}
                      value={justification}
                      onChange={(e) => setJustification(e.target.value)}
                      placeholder="Enter legal justification for override (e.g., Processing falls under GDPR Art. 9(2)(a) explicit consent with localized on-device processing)..."
                      className="w-full bg-black/30 border border-white/10 rounded-2xl p-4 text-sm text-white/90 placeholder-white/30 focus:outline-none focus:border-white/40 focus:ring-1 focus:ring-white/30 backdrop-blur-md leading-relaxed transition-all duration-200 ease-out"
                    />
                    {overrideError && (
                      <div className="text-xs text-rose-400 animate-in fade-in duration-200">{overrideError}</div>
                    )}
                    <button
                      onClick={handleOverride}
                      disabled={isOverriding || !justification.trim() || isLoading}
                      className="px-6 py-3 bg-amber-500 hover:bg-amber-400 text-slate-950 font-semibold rounded-xl text-sm transition-all duration-200 ease-out disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2 active:scale-95 shadow-md shadow-amber-500/20"
                    >
                      {isOverriding ? (
                        <>
                          <span className="inline-block animate-spin">⏳</span>
                          <span>Committing Override Block...</span>
                        </>
                      ) : (
                        <>
                          <span>🧑‍⚖️</span>
                          <span>Override Judgment & Append to Ledger</span>
                        </>
                      )}
                    </button>
                  </div>
                )}
              </section>
            )}
          </div>
        )}
      </main>

      {/* Redesigned Elevated Apple Liquid Glass Ledger History Modal */}
      {showLedgerModal && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-2xl z-50 flex items-center justify-center p-4 sm:p-6 transition-all duration-200 ease-out animate-in fade-in">
          <div className="bg-[#0b0c10]/95 backdrop-blur-3xl border border-white/20 rounded-[2.5rem] max-w-4xl w-full max-h-[88vh] flex flex-col shadow-[0_0_50px_rgba(0,0,0,0.8),0_24px_80px_rgba(0,0,0,0.9)] overflow-hidden relative z-50">
            {/* Modal Header */}
            <div className="px-8 py-6 border-b border-white/10 flex items-center justify-between bg-white/[0.03]">
              <div className="flex items-center space-x-3.5">
                <div className="h-11 w-11 rounded-2xl bg-indigo-500/15 border border-indigo-500/30 flex items-center justify-center text-lg shadow-inner">
                  ⛓️
                </div>
                <div>
                  <h3 className="font-medium text-white/95 text-lg tracking-tight">
                    PostgreSQL Cryptographic Ledger Explorer
                  </h3>
                  <p className="text-xs text-white/50 font-light">
                    {user?.org_name || "Tenant"} Immutable SHA-256 Audit Chain Verified
                  </p>
                </div>
              </div>
              <button
                onClick={() => setShowLedgerModal(false)}
                className="text-white/50 hover:text-white text-sm h-9 w-9 rounded-2xl hover:bg-white/10 border border-white/10 transition-all duration-200 ease-out flex items-center justify-center active:scale-90"
              >
                ✕
              </button>
            </div>

            {/* Modal Body & Blockchain Visual */}
            <div className="p-6 sm:p-8 overflow-y-auto space-y-6 flex-1 text-xs">
              {isLoadingLedger && (
                <div className="text-center py-16 space-y-3">
                  <div className="inline-block animate-spin text-2xl text-indigo-400">⏳</div>
                  <div className="text-white/50 text-sm font-light">Verifying SHA-256 hash continuity across blocks...</div>
                </div>
              )}

              {ledgerData && (
                <>
                  {/* Ledger Authenticity Metric Bar */}
                  <div className="flex flex-wrap items-center justify-between gap-4 p-4 rounded-2xl bg-white/[0.04] border border-white/15 backdrop-blur-md shadow-inner">
                    <div className="flex items-center space-x-4">
                      <div>
                        <span className="text-white/40 text-[10px] uppercase tracking-wider block font-sans">
                          Total Committed Blocks
                        </span>
                        <span className="text-white/95 font-semibold text-sm font-mono">
                          {ledgerData.total}
                        </span>
                      </div>
                      <div className="h-8 w-[1px] bg-white/10" />
                      <div>
                        <span className="text-white/40 text-[10px] uppercase tracking-wider block font-sans">
                          Chain Verification
                        </span>
                        {ledgerData.chain_valid ? (
                          <span className="text-emerald-400 font-semibold text-sm flex items-center space-x-1.5">
                            <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse"></span>
                            <span>Valid Cryptographic Chain</span>
                          </span>
                        ) : (
                          <span className="text-rose-400 font-semibold text-sm flex items-center space-x-1.5">
                            <span className="h-2 w-2 rounded-full bg-rose-400 animate-pulse"></span>
                            <span>Tampering / Fork Detected</span>
                          </span>
                        )}
                      </div>
                    </div>
                    <button
                      onClick={fetchLedgerHistory}
                      className="px-4 py-2 rounded-xl bg-white/10 hover:bg-white/20 text-white font-medium text-xs transition-all duration-200 ease-out active:scale-95 font-sans border border-white/10"
                    >
                      Re-verify Chain
                    </button>
                  </div>

                  {/* Visual Blockchain Flow */}
                  <div className="space-y-4">
                    {ledgerData.blocks.map((block, idx) => (
                      <div
                        key={block.audit_id}
                        className="bg-white/[0.04] hover:bg-white/[0.10] border border-white/10 hover:border-white/25 rounded-2xl p-5 space-y-3.5 transition-all duration-200 ease-out backdrop-blur-md cursor-pointer group shadow-sm"
                      >
                        {/* Block Header */}
                        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/5 pb-3">
                          <div className="flex items-center space-x-2.5">
                            <span className="h-6 w-6 rounded-lg bg-indigo-500/20 border border-indigo-500/30 text-indigo-300 font-mono text-[10px] flex items-center justify-center font-bold shadow-inner">
                              #{ledgerData.total - idx}
                            </span>
                            <span className="text-white/95 font-medium text-xs truncate max-w-sm sm:max-w-md font-sans group-hover:text-white transition-colors">
                              {block.user_query}
                            </span>
                          </div>
                          <div className="flex items-center space-x-2">
                            {getBlockStatusPill(block)}
                            <span className="text-[11px] text-white/40 font-mono">
                              {formatTimestamp(block.timestamp)}
                            </span>
                            {isAdmin && (
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleDeletePrompt(block.audit_id);
                                }}
                                className="text-white/40 hover:text-rose-400 p-1 rounded-lg hover:bg-rose-500/10 border border-transparent hover:border-rose-500/20 transition-all duration-200 active:scale-90"
                                title="Delete Prompt / Audit Entry (Admin Only)"
                              >
                                🗑️
                              </button>
                            )}
                          </div>
                        </div>

                        {/* Cryptographic Linkage Info */}
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px] font-mono">
                          <div className="bg-black/60 group-hover:bg-black/80 p-2.5 rounded-xl border border-white/5 group-hover:border-white/15 flex items-center justify-between transition-all duration-200">
                            <div className="truncate mr-2">
                              <span className="text-indigo-400 block text-[9px] uppercase font-sans font-medium">Tx Hash</span>
                              <span className="text-indigo-200 font-semibold">{truncateHash(block.tx_hash)}</span>
                            </div>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                copyToClipboard(block.tx_hash, `modal_tx_${idx}`);
                              }}
                              className="text-[10px] text-white/60 hover:text-white px-2 py-0.5 rounded bg-white/10 hover:bg-white/20 transition-all duration-200 active:scale-90 font-sans"
                            >
                              {copiedKey === `modal_tx_${idx}` ? "Copied!" : "Copy"}
                            </button>
                          </div>

                          <div className="bg-black/60 group-hover:bg-black/80 p-2.5 rounded-xl border border-white/5 group-hover:border-white/15 flex items-center justify-between transition-all duration-200">
                            <div className="truncate mr-2">
                              <span className="text-white/40 block text-[9px] uppercase font-sans font-medium">Prev Hash</span>
                              <span className="text-white/60">{truncateHash(block.prev_hash)}</span>
                            </div>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                copyToClipboard(block.prev_hash, `modal_prev_${idx}`);
                              }}
                              className="text-[10px] text-white/60 hover:text-white px-2 py-0.5 rounded bg-white/10 hover:bg-white/20 transition-all duration-200 active:scale-90 font-sans"
                            >
                              {copiedKey === `modal_prev_${idx}` ? "Copied!" : "Copy"}
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
