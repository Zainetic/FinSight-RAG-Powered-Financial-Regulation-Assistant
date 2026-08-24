"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useAuth } from "../context/AuthContext";

// =====================================================================
// Data Contracts
// =====================================================================

interface TransactionFormState {
  tx_id: string;
  sender_name: string;
  sender_iban: string;
  sender_country: string;
  receiver_name: string;
  receiver_iban: string;
  receiver_country: string;
  amount: number | string;
  currency: string;
  asset_type: string;
  sender_kyc_level: "basic" | "standard" | "enhanced";
}

interface ScrubbedPayload {
  tx_id: string;
  sender_name: string;
  sender_iban: string;
  sender_country: string;
  receiver_name: string;
  receiver_iban: string;
  receiver_country: string;
  amount: number;
  currency: string;
  asset_type: string;
  sender_kyc_level: string;
}

interface GatekeeperResponse {
  verdict: "PASS" | "FAIL";
  risk_score: number;
  rule_triggered: string | null;
  legal_basis: string | null;
  sha256_audit_hash: string;
  timestamp: string;
  raw_payload_preview: Record<string, unknown>;
  scrubbed_payload_sent_to_engine: ScrubbedPayload;
}

interface LedgerRecord {
  id?: string;
  transaction_id: string;
  payload_data?: Record<string, unknown>;
  verdict: "PASS" | "FAIL" | string;
  risk_score: number;
  rule_triggered?: string | null;
  legal_basis?: string | null;
  sha256_hash: string;
  timestamp?: string | null;
}

const DEFAULT_TRANSACTION: TransactionFormState = {
  tx_id: "TX-2026-894102",
  sender_name: "Fintech Core Ltd",
  sender_iban: "FR1420041010050500013M02606",
  sender_country: "FR",
  receiver_name: "Parisian Merchant SAS",
  receiver_iban: "FR7630004000010000000000000",
  receiver_country: "FR",
  amount: 2450,
  currency: "EUR",
  asset_type: "SEPA_INSTANT",
  sender_kyc_level: "standard",
};

export default function SimulatorPage() {
  const { token, user } = useAuth();

  const [form, setForm] = useState<TransactionFormState>(DEFAULT_TRANSACTION);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [result, setResult] = useState<GatekeeperResponse | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  // Live Ledger History State
  const [ledgerHistory, setLedgerHistory] = useState<LedgerRecord[]>([]);
  const [isLoadingLedger, setIsLoadingLedger] = useState<boolean>(false);

  // Fetch Ledger History
  const fetchLedger = async () => {
    setIsLoadingLedger(true);
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const headers: Record<string, string> = {};
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }

      const res = await fetch(`${apiUrl}/api/v1/transactions/ledger`, {
        method: "GET",
        credentials: "include",
        headers,
      });

      if (res.ok) {
        const data: LedgerRecord[] = await res.json();
        setLedgerHistory(data);
      }
    } catch (err) {
      console.error("Failed to fetch transaction ledger history:", err);
    } finally {
      setIsLoadingLedger(false);
    }
  };

  // Initial Fetch on Component Mount
  useEffect(() => {
    fetchLedger();
  }, [token]);

  // Preset Handlers
  const applyPreset = (type: "routine" | "offshore" | "sanctioned") => {
    setErrorMessage(null);
    if (type === "routine") {
      setForm({
        tx_id: `TX-${Date.now().toString().slice(-6)}`,
        sender_name: "Jean-Pierre Laurent",
        sender_iban: "FR1420041010050500013M02606",
        sender_country: "FR",
        receiver_name: "Lyon Logistics SARL",
        receiver_iban: "FR7630004000010000000000000",
        receiver_country: "FR",
        amount: 2450,
        currency: "EUR",
        asset_type: "SEPA_INSTANT",
        sender_kyc_level: "standard",
      });
    } else if (type === "offshore") {
      setForm({
        tx_id: `TX-${Date.now().toString().slice(-6)}`,
        sender_name: "Global Capital Venture AG",
        sender_iban: "DE89370400440532013000",
        sender_country: "DE",
        receiver_name: "Grand Cayman Wealth Trust Ltd",
        receiver_iban: "KY96BOFI00000012345678",
        receiver_country: "KY",
        amount: 45000,
        currency: "EUR",
        asset_type: "FIAT_WIRE",
        sender_kyc_level: "standard",
      });
    } else if (type === "sanctioned") {
      setForm({
        tx_id: `TX-${Date.now().toString().slice(-6)}`,
        sender_name: "Aether Trade Holdings",
        sender_iban: "GB29NWBK60161331926819",
        sender_country: "GB",
        receiver_name: "Damascus Allied Import Export",
        receiver_iban: "SY9300010000001234567890",
        receiver_country: "SY",
        amount: 12000,
        currency: "EUR",
        asset_type: "FIAT_WIRE",
        sender_kyc_level: "enhanced",
      });
    }
  };

  const copyToClipboard = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setErrorMessage(null);

    const payload = {
      ...form,
      amount: Number(form.amount),
      sender_country: form.sender_country.trim().toUpperCase(),
      receiver_country: form.receiver_country.trim().toUpperCase(),
    };

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      };
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }

      const res = await fetch(`${apiUrl}/api/v1/transactions/evaluate`, {
        method: "POST",
        credentials: "include",
        headers,
        body: JSON.stringify(payload),
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        throw new Error(data.detail || `Server returned HTTP ${res.status}`);
      }

      setResult(data as GatekeeperResponse);

      // Real-time refresh of immutable ledger audit trail
      await fetchLedger();
    } catch (err: unknown) {
      const message =
        err instanceof Error
          ? err.message
          : "Failed to dispatch transaction to gatekeeper service.";
      setErrorMessage(message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-slate-900 via-[#120e24] to-slate-950 text-white/90 font-sans selection:bg-indigo-500/30 selection:text-white relative overflow-x-hidden flex flex-col">
      {/* Ambient Glassmorphism Gradient Glow Orbs */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden z-0">
        <div className="absolute -top-48 -right-48 w-[700px] h-[700px] bg-purple-600/15 rounded-full blur-[150px] animate-pulse" />
        <div className="absolute top-1/2 -left-48 w-[600px] h-[600px] bg-indigo-600/15 rounded-full blur-[140px]" />
        <div className="absolute -bottom-48 right-1/4 w-[650px] h-[650px] bg-sky-600/10 rounded-full blur-[160px]" />
      </div>

      {/* Navigation Header */}
      <header className="border-b border-white/10 bg-white/[0.02] backdrop-blur-2xl sticky top-0 z-40 transition-all duration-200">
        <div className="max-w-7xl mx-auto px-6 sm:px-8 h-20 flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <Link
              href="/"
              className="h-10 w-10 rounded-2xl bg-white/[0.08] border border-white/15 flex items-center justify-center text-lg hover:bg-white/15 transition-all duration-200 ease-out active:scale-95 shadow-inner"
              title="Return to Dashboard"
            >
              <span>&larr;</span>
            </Link>
            <div>
              <div className="flex items-center space-x-2.5">
                <span className="font-semibold text-lg tracking-tight text-white/95">
                  FinSight Gatekeeper
                </span>
                <span className="text-[11px] px-2.5 py-0.5 rounded-full bg-indigo-500/15 text-indigo-300 border border-indigo-500/25 font-mono">
                  Sandbox Simulator
                </span>
              </div>
              <p className="text-xs text-white/50 font-light hidden sm:block">
                Machine-to-Machine Financial Compliance & Zero-Trust PII Scrubbing
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-3">
            <Link
              href="/"
              className="text-xs px-4 py-2 rounded-xl bg-white/[0.06] hover:bg-white/[0.12] text-white/80 hover:text-white border border-white/15 backdrop-blur-xl transition-all duration-200 ease-out active:scale-95"
            >
              Compliance Dashboard
            </Link>
            {user?.role === "MASTER_ADMIN" && (
              <Link
                href="/admin"
                className="text-xs px-3.5 py-2 rounded-xl bg-purple-500/10 hover:bg-purple-500/20 text-purple-200 border border-purple-500/20 backdrop-blur-xl transition-all duration-200 ease-out active:scale-95"
              >
                Team Mgmt
              </Link>
            )}
          </div>
        </div>
      </header>

      {/* Main Flowing Grid Canvas */}
      <main className="max-w-7xl mx-auto px-6 sm:px-8 py-10 flex-1 w-full space-y-10 relative z-10">
        {/* Hero & Preset Buttons */}
        <section className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <h1 className="text-3xl sm:text-4xl font-light tracking-tight text-white/95">
                Transaction Gatekeeper Simulator
              </h1>
              <p className="text-xs sm:text-sm text-white/60 font-light mt-1">
                Simulate real-time M2M payload processing, automated sanctions screening, and zero-trust PII sanitization.
              </p>
            </div>

            {/* Presets */}
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs uppercase tracking-wider text-white/40 font-mono font-medium mr-1">
                Presets:
              </span>
              <button
                type="button"
                onClick={() => applyPreset("routine")}
                className="text-xs px-3.5 py-2 rounded-xl bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 border border-emerald-500/25 transition-all duration-200 ease-out active:scale-95 flex items-center space-x-1.5"
              >
                <span>🟢</span>
                <span>Routine (€2,450 FR&rarr;FR)</span>
              </button>
              <button
                type="button"
                onClick={() => applyPreset("offshore")}
                className="text-xs px-3.5 py-2 rounded-xl bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/25 transition-all duration-200 ease-out active:scale-95 flex items-center space-x-1.5"
              >
                <span>🟡</span>
                <span>Offshore (€45k &rarr; KY)</span>
              </button>
              <button
                type="button"
                onClick={() => applyPreset("sanctioned")}
                className="text-xs px-3.5 py-2 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/25 transition-all duration-200 ease-out active:scale-95 flex items-center space-x-1.5"
              >
                <span>🔴</span>
                <span>Sanctioned (€12k &rarr; SY)</span>
              </button>
            </div>
          </div>
        </section>

        {errorMessage && (
          <div className="p-4 rounded-2xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs flex items-center space-x-3 animate-in fade-in duration-200">
            <span>⚠️</span>
            <span>{errorMessage}</span>
          </div>
        )}

        {/* 2-Panel Split Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          {/* =====================================================================
              Left Panel: Editable Inbound Transaction Form (5 Cols)
          ===================================================================== */}
          <div className="lg:col-span-5">
            <div className="bg-white/5 backdrop-blur-2xl border border-white/10 shadow-[0_8px_32px_0_rgba(0,0,0,0.37)] rounded-[2.5rem] p-6 sm:p-8 space-y-6">
              <div className="flex items-center justify-between border-b border-white/5 pb-4">
                <div className="flex items-center space-x-3">
                  <span className="text-xl">📤</span>
                  <h2 className="text-lg sm:text-xl font-light text-white/95 tracking-tight">
                    Inbound Transaction Payload
                  </h2>
                </div>
                <span className="text-[11px] font-mono text-white/40">POST /evaluate</span>
              </div>

              <form onSubmit={handleSubmit} className="space-y-4">
                {/* Tx ID & Amount */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <label className="text-[11px] uppercase font-mono tracking-wider text-white/50 block">
                      Transaction ID
                    </label>
                    <input
                      type="text"
                      required
                      value={form.tx_id}
                      onChange={(e) => setForm({ ...form, tx_id: e.target.value })}
                      className="w-full bg-black/30 border border-white/10 rounded-xl px-3.5 py-2.5 text-xs font-mono text-white/90 focus:outline-none focus:border-white/40 focus:ring-1 focus:ring-white/30 backdrop-blur-md"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-[11px] uppercase font-mono tracking-wider text-white/50 block">
                      Amount ({form.currency})
                    </label>
                    <input
                      type="number"
                      required
                      step="any"
                      min="0.01"
                      value={form.amount}
                      onChange={(e) => setForm({ ...form, amount: e.target.value })}
                      className="w-full bg-black/30 border border-white/10 rounded-xl px-3.5 py-2.5 text-xs font-mono text-white/90 focus:outline-none focus:border-white/40 focus:ring-1 focus:ring-white/30 backdrop-blur-md font-semibold text-emerald-400"
                    />
                  </div>
                </div>

                {/* Currency, Asset Type, KYC Tier */}
                <div className="grid grid-cols-3 gap-2.5">
                  <div className="space-y-1">
                    <label className="text-[11px] uppercase font-mono tracking-wider text-white/50 block">
                      Currency
                    </label>
                    <input
                      type="text"
                      required
                      value={form.currency}
                      onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })}
                      className="w-full bg-black/30 border border-white/10 rounded-xl px-3 py-2.5 text-xs font-mono text-white/90 focus:outline-none focus:border-white/40 focus:ring-1 focus:ring-white/30 backdrop-blur-md"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-[11px] uppercase font-mono tracking-wider text-white/50 block">
                      Asset Type
                    </label>
                    <select
                      value={form.asset_type}
                      onChange={(e) => setForm({ ...form, asset_type: e.target.value })}
                      className="w-full bg-black/30 border border-white/10 rounded-xl px-2.5 py-2.5 text-xs font-mono text-white/90 focus:outline-none focus:border-white/40 focus:ring-1 focus:ring-white/30 backdrop-blur-md"
                    >
                      <option value="SEPA_INSTANT" className="bg-slate-900">SEPA_INSTANT</option>
                      <option value="FIAT_WIRE" className="bg-slate-900">FIAT_WIRE</option>
                      <option value="SWIFT_GPI" className="bg-slate-900">SWIFT_GPI</option>
                      <option value="CRYPTO_TRANSFER" className="bg-slate-900">CRYPTO_TRANSFER</option>
                    </select>
                  </div>
                  <div className="space-y-1">
                    <label className="text-[11px] uppercase font-mono tracking-wider text-white/50 block">
                      Sender KYC
                    </label>
                    <select
                      value={form.sender_kyc_level}
                      onChange={(e) =>
                        setForm({
                          ...form,
                          sender_kyc_level: e.target.value as "basic" | "standard" | "enhanced",
                        })
                      }
                      className="w-full bg-black/30 border border-white/10 rounded-xl px-2.5 py-2.5 text-xs font-mono text-white/90 focus:outline-none focus:border-white/40 focus:ring-1 focus:ring-white/30 backdrop-blur-md"
                    >
                      <option value="basic" className="bg-slate-900">basic</option>
                      <option value="standard" className="bg-slate-900">standard</option>
                      <option value="enhanced" className="bg-slate-900">enhanced (EDD)</option>
                    </select>
                  </div>
                </div>

                {/* Sender Details */}
                <div className="p-4 rounded-2xl bg-black/20 border border-white/5 space-y-3">
                  <div className="text-[11px] uppercase font-mono tracking-wider text-indigo-300 font-medium flex items-center justify-between">
                    <span>Sender Info</span>
                    <span className="text-white/40">Originator</span>
                  </div>
                  <div className="space-y-2">
                    <div>
                      <input
                        type="text"
                        required
                        placeholder="Sender Full Name / Legal Entity"
                        value={form.sender_name}
                        onChange={(e) => setForm({ ...form, sender_name: e.target.value })}
                        className="w-full bg-black/40 border border-white/10 rounded-xl px-3.5 py-2 text-xs text-white/90 placeholder-white/30 focus:outline-none focus:border-white/40 focus:ring-1 focus:ring-white/30 font-light"
                      />
                    </div>
                    <div className="grid grid-cols-4 gap-2">
                      <div className="col-span-3">
                        <input
                          type="text"
                          required
                          placeholder="Sender IBAN"
                          value={form.sender_iban}
                          onChange={(e) => setForm({ ...form, sender_iban: e.target.value })}
                          className="w-full bg-black/40 border border-white/10 rounded-xl px-3.5 py-2 text-xs font-mono text-white/90 placeholder-white/30 focus:outline-none focus:border-white/40 focus:ring-1 focus:ring-white/30"
                        />
                      </div>
                      <div>
                        <input
                          type="text"
                          required
                          maxLength={2}
                          placeholder="Country (ISO)"
                          value={form.sender_country}
                          onChange={(e) =>
                            setForm({ ...form, sender_country: e.target.value.toUpperCase() })
                          }
                          className="w-full bg-black/40 border border-white/10 rounded-xl px-2 py-2 text-xs font-mono text-center text-white/90 placeholder-white/30 focus:outline-none focus:border-white/40 focus:ring-1 focus:ring-white/30 uppercase font-bold"
                        />
                      </div>
                    </div>
                  </div>
                </div>

                {/* Receiver Details */}
                <div className="p-4 rounded-2xl bg-black/20 border border-white/5 space-y-3">
                  <div className="text-[11px] uppercase font-mono tracking-wider text-purple-300 font-medium flex items-center justify-between">
                    <span>Receiver Info</span>
                    <span className="text-white/40">Beneficiary</span>
                  </div>
                  <div className="space-y-2">
                    <div>
                      <input
                        type="text"
                        required
                        placeholder="Receiver Full Name / Entity"
                        value={form.receiver_name}
                        onChange={(e) => setForm({ ...form, receiver_name: e.target.value })}
                        className="w-full bg-black/40 border border-white/10 rounded-xl px-3.5 py-2 text-xs text-white/90 placeholder-white/30 focus:outline-none focus:border-white/40 focus:ring-1 focus:ring-white/30 font-light"
                      />
                    </div>
                    <div className="grid grid-cols-4 gap-2">
                      <div className="col-span-3">
                        <input
                          type="text"
                          required
                          placeholder="Receiver IBAN"
                          value={form.receiver_iban}
                          onChange={(e) => setForm({ ...form, receiver_iban: e.target.value })}
                          className="w-full bg-black/40 border border-white/10 rounded-xl px-3.5 py-2 text-xs font-mono text-white/90 placeholder-white/30 focus:outline-none focus:border-white/40 focus:ring-1 focus:ring-white/30"
                        />
                      </div>
                      <div>
                        <input
                          type="text"
                          required
                          maxLength={2}
                          placeholder="Country (ISO)"
                          value={form.receiver_country}
                          onChange={(e) =>
                            setForm({ ...form, receiver_country: e.target.value.toUpperCase() })
                          }
                          className="w-full bg-black/40 border border-white/10 rounded-xl px-2 py-2 text-xs font-mono text-center text-white/90 placeholder-white/30 focus:outline-none focus:border-white/40 focus:ring-1 focus:ring-white/30 uppercase font-bold"
                        />
                      </div>
                    </div>
                  </div>
                </div>

                {/* Submit Action */}
                <button
                  type="submit"
                  disabled={isLoading}
                  className="w-full py-4 px-6 rounded-2xl bg-white hover:bg-white/90 text-slate-950 font-medium text-sm transition-all duration-200 ease-out disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center space-x-2.5 active:scale-95 shadow-[0_4px_20px_0_rgba(255,255,255,0.2)] font-mono"
                >
                  {isLoading ? (
                    <>
                      <span className="inline-block animate-spin">⏳</span>
                      <span>Evaluating AML & Sanctions Policy...</span>
                    </>
                  ) : (
                    <>
                      <span>⚡</span>
                      <span>Dispatch to FinSight Gatekeeper</span>
                      <span>&rarr;</span>
                    </>
                  )}
                </button>
              </form>
            </div>
          </div>

          {/* =====================================================================
              Right Panel: Real-Time Regulatory Verdict & Zero-Trust Visualizer (7 Cols)
          ===================================================================== */}
          <div className="lg:col-span-7 space-y-6">
            {/* Status & Verdict Card */}
            {result ? (
              <div className="space-y-6 animate-in fade-in duration-300">
                {/* 1. Verdict Metric Hero Card */}
                <div
                  className={`bg-white/5 backdrop-blur-2xl border shadow-[0_8px_32px_0_rgba(0,0,0,0.37)] rounded-[2.5rem] p-6 sm:p-8 relative overflow-hidden transition-all duration-200 ${
                    result.verdict === "PASS"
                      ? "border-emerald-500/30 bg-gradient-to-br from-emerald-950/20 via-transparent to-transparent"
                      : "border-rose-500/30 bg-gradient-to-br from-rose-950/20 via-transparent to-transparent"
                  }`}
                >
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-white/10 pb-5">
                    <div>
                      <div className="text-[10px] uppercase font-mono tracking-wider text-white/40">
                        Gatekeeper Regulatory Decision
                      </div>
                      <div className="flex items-center space-x-3 mt-1">
                        {result.verdict === "PASS" ? (
                          <>
                            <span className="text-3xl">🟢</span>
                            <span className="text-3xl font-bold tracking-tight text-emerald-400">
                              PASS (Approved)
                            </span>
                          </>
                        ) : (
                          <>
                            <span className="text-3xl">🔴</span>
                            <span className="text-3xl font-bold tracking-tight text-rose-400">
                              FAIL (Blocked)
                            </span>
                          </>
                        )}
                      </div>
                    </div>

                    {/* Risk Score Pill */}
                    <div className="flex items-center space-x-3 bg-black/40 px-4 py-2.5 rounded-2xl border border-white/10 backdrop-blur-md">
                      <div className="text-right">
                        <span className="text-[10px] uppercase font-mono text-white/40 block">
                          AML Risk Score
                        </span>
                        <span
                          className={`text-xl font-mono font-bold ${
                            result.risk_score > 75
                              ? "text-rose-400"
                              : result.risk_score > 30
                              ? "text-amber-400"
                              : "text-emerald-400"
                          }`}
                        >
                          {result.risk_score} / 100
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Rule & Legal Basis Info */}
                  <div className="mt-5 space-y-3 text-xs">
                    <div className="bg-black/30 p-4 rounded-2xl border border-white/5 space-y-1">
                      <span className="text-[10px] uppercase font-mono text-white/40 block">
                        Triggered Regulatory Rule
                      </span>
                      <p className="text-white/90 font-medium">
                        {result.rule_triggered || "Standard Low-Risk Flow"}
                      </p>
                    </div>

                    <div className="bg-black/30 p-4 rounded-2xl border border-white/5 space-y-1">
                      <span className="text-[10px] uppercase font-mono text-white/40 block">
                        Statutory Legal Basis
                      </span>
                      <p className="text-white/70 font-light">
                        {result.legal_basis || "EU AMLD5 & PSD2 Compliance Standard"}
                      </p>
                    </div>

                    {/* SHA-256 Audit Digest */}
                    <div className="bg-black/40 p-4 rounded-2xl border border-white/10 flex items-center justify-between font-mono">
                      <div className="truncate mr-3">
                        <span className="text-[9px] uppercase tracking-wider text-indigo-300 block font-sans">
                          SHA-256 Cryptographic Audit Hash
                        </span>
                        <span className="text-white/80 text-xs truncate block">
                          {result.sha256_audit_hash}
                        </span>
                      </div>
                      <button
                        type="button"
                        onClick={() =>
                          copyToClipboard(result.sha256_audit_hash, "sha256_hash")
                        }
                        className="text-xs px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white font-sans transition-all duration-200 active:scale-95 shrink-0 border border-white/10"
                      >
                        {copiedKey === "sha256_hash" ? "Copied!" : "Copy"}
                      </button>
                    </div>
                  </div>
                </div>

                {/* 2. Side-by-Side Data Visualizer (Raw vs Scrubbed Zero-Trust Payload) */}
                <div className="bg-white/5 backdrop-blur-2xl border border-white/10 shadow-[0_8px_32px_0_rgba(0,0,0,0.37)] rounded-[2.5rem] p-6 sm:p-8 space-y-4">
                  <div className="flex items-center justify-between border-b border-white/5 pb-3">
                    <div className="flex items-center space-x-2.5">
                      <span className="text-lg">🛡️</span>
                      <h3 className="text-base font-light text-white/95">
                        Zero-Trust PII Sanitization Inspection
                      </h3>
                    </div>
                    <span className="text-[10px] font-mono px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
                      PII MASKED AT INGRESS
                    </span>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs font-mono">
                    {/* Left: Raw Unsanitized Inbound Payload */}
                    <div className="space-y-2">
                      <div className="flex items-center justify-between text-white/50 text-[11px] uppercase tracking-wider font-sans">
                        <span className="text-rose-300/90 font-medium">1. Raw Inbound Payload</span>
                        <span className="text-[10px] text-white/30">(Contains PII)</span>
                      </div>
                      <div className="bg-black/60 p-4 rounded-2xl border border-rose-500/20 overflow-x-auto max-h-80 shadow-inner">
                        <pre className="text-[11px] text-rose-200/90 leading-relaxed">
                          {JSON.stringify(result.raw_payload_preview, null, 2)}
                        </pre>
                      </div>
                    </div>

                    {/* Right: Zero-Trust Scrubbed Payload */}
                    <div className="space-y-2">
                      <div className="flex items-center justify-between text-white/50 text-[11px] uppercase tracking-wider font-sans">
                        <span className="text-emerald-300/90 font-medium">2. Scrubbed Engine Payload</span>
                        <span className="text-[10px] text-emerald-400/60">(Zero PII Leaks)</span>
                      </div>
                      <div className="bg-black/60 p-4 rounded-2xl border border-emerald-500/20 overflow-x-auto max-h-80 shadow-inner">
                        <pre className="text-[11px] text-emerald-200/90 leading-relaxed">
                          {JSON.stringify(result.scrubbed_payload_sent_to_engine, null, 2)}
                        </pre>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              /* Empty State */
              <div className="bg-white/5 backdrop-blur-2xl border border-white/10 shadow-[0_8px_32px_0_rgba(0,0,0,0.37)] rounded-[2.5rem] p-12 text-center space-y-4 flex flex-col items-center justify-center min-h-[420px]">
                <div className="h-16 w-16 rounded-3xl bg-white/[0.04] border border-white/10 flex items-center justify-center text-3xl shadow-inner">
                  ⚖️
                </div>
                <h3 className="text-xl font-light text-white/90 tracking-tight">
                  Awaiting Transaction Dispatch
                </h3>
                <p className="text-xs sm:text-sm text-white/50 font-light max-w-md leading-relaxed">
                  Select one of the demo presets above or customize the inbound payload parameters on the left, then click <strong>Dispatch to FinSight Gatekeeper</strong> to evaluate compliance in real-time.
                </p>
                <div className="pt-2 flex items-center space-x-2 text-[11px] font-mono text-white/40">
                  <span>Zero-Trust PII Scrubbing</span>
                  <span>•</span>
                  <span>FATF Embargo Rules</span>
                  <span>•</span>
                  <span>SHA-256 Audit Trail</span>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* =====================================================================
            Full-Width Live Transaction Audit Trail Ledger Table
        ===================================================================== */}
        <section className="bg-white/5 backdrop-blur-2xl border border-white/10 shadow-[0_8px_32px_0_rgba(0,0,0,0.37)] rounded-[2.5rem] p-6 sm:p-8 space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-white/5 pb-4">
            <div className="flex items-center space-x-3">
              <div className="h-10 w-10 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-lg shadow-inner">
                ⛓️
              </div>
              <div>
                <div className="flex items-center space-x-2.5">
                  <h2 className="text-lg sm:text-xl font-light text-white/95 tracking-tight">
                    Immutable Audit Trail &amp; Ledger
                  </h2>
                  <span className="text-[10px] font-mono px-2.5 py-0.5 rounded-full bg-indigo-500/15 text-indigo-300 border border-indigo-500/25">
                    PostgreSQL Live Sync
                  </span>
                </div>
                <p className="text-xs text-white/50 font-light">
                  Real-time transaction compliance logs with SHA-256 cryptographic verification digests.
                </p>
              </div>
            </div>

            <div className="flex items-center space-x-3">
              <button
                type="button"
                onClick={fetchLedger}
                disabled={isLoadingLedger}
                className="text-xs px-3.5 py-2 rounded-xl bg-white/[0.06] hover:bg-white/[0.12] text-white/80 hover:text-white border border-white/15 backdrop-blur-xl transition-all duration-200 ease-out active:scale-95 flex items-center space-x-1.5 font-mono"
              >
                <span className={isLoadingLedger ? "inline-block animate-spin" : ""}>🔄</span>
                <span>{isLoadingLedger ? "Syncing..." : "Refresh Ledger"}</span>
              </button>
            </div>
          </div>

          {/* Table Container */}
          <div className="overflow-x-auto rounded-2xl border border-white/5 bg-black/30">
            <table className="w-full text-left text-xs font-mono">
              <thead className="bg-white/[0.03] border-b border-white/10 text-white/50 uppercase tracking-wider text-[10px]">
                <tr>
                  <th className="py-3.5 px-4 font-medium">Timestamp (UTC)</th>
                  <th className="py-3.5 px-4 font-medium">Transaction ID</th>
                  <th className="py-3.5 px-4 font-medium">Verdict</th>
                  <th className="py-3.5 px-4 font-medium">Risk Score</th>
                  <th className="py-3.5 px-4 font-medium">SHA-256 Cryptographic Digest</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5 text-white/80">
                {ledgerHistory.length > 0 ? (
                  ledgerHistory.map((item, idx) => {
                    const isPass = item.verdict === "PASS";
                    const formattedTime = item.timestamp
                      ? new Date(item.timestamp).toLocaleString("en-US", {
                          month: "short",
                          day: "numeric",
                          hour: "2-digit",
                          minute: "2-digit",
                          second: "2-digit",
                          hour12: false,
                        })
                      : "Just now";

                    return (
                      <tr
                        key={item.id || item.transaction_id || idx}
                        className="hover:bg-white/[0.02] transition-colors"
                      >
                        <td className="py-3.5 px-4 text-white/50 text-[11px] whitespace-nowrap">
                          {formattedTime}
                        </td>
                        <td className="py-3.5 px-4 font-semibold text-white/90">
                          {item.transaction_id}
                        </td>
                        <td className="py-3.5 px-4">
                          <span
                            className={`inline-flex items-center space-x-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold ${
                              isPass
                                ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/25"
                                : "bg-rose-500/10 text-rose-400 border border-rose-500/25"
                            }`}
                          >
                            <span>{isPass ? "🟢" : "🔴"}</span>
                            <span>{item.verdict}</span>
                          </span>
                        </td>
                        <td className="py-3.5 px-4">
                          <span
                            className={`font-bold ${
                              item.risk_score > 75
                                ? "text-rose-400"
                                : item.risk_score > 30
                                ? "text-amber-400"
                                : "text-emerald-400"
                            }`}
                          >
                            {item.risk_score} / 100
                          </span>
                        </td>
                        <td className="py-3.5 px-4 text-white/60">
                          <div className="flex items-center space-x-2">
                            <span className="truncate max-w-[200px] sm:max-w-[280px]">
                              {item.sha256_hash}
                            </span>
                            <button
                              type="button"
                              onClick={() =>
                                copyToClipboard(item.sha256_hash, `ledger_${idx}`)
                              }
                              className="text-[10px] px-2 py-0.5 rounded bg-white/10 hover:bg-white/20 text-white transition-all duration-150 active:scale-95 shrink-0"
                            >
                              {copiedKey === `ledger_${idx}` ? "Copied" : "Copy"}
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })
                ) : (
                  <tr>
                    <td
                      colSpan={5}
                      className="py-8 text-center text-white/40 text-xs font-light font-sans"
                    >
                      {isLoadingLedger
                        ? "Loading audit ledger entries..."
                        : "No evaluated transactions found. Dispatch a transaction above to create the first ledger entry."}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </main>
    </div>
  );
}
