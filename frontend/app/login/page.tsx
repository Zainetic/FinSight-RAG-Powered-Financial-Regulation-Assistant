"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "../context/AuthContext";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const { login } = useAuth();
  const router = useRouter();

  const handleLogin = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!email.trim() || !password || isLoading) return;

    setIsLoading(true);
    setErrorMessage(null);

    try {
      const res = await fetch("http://localhost:8000/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: email.trim(),
          password,
        }),
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        throw new Error(data.detail || `Authentication failed (${res.status})`);
      }

      // Save token & user to Auth Context
      login(data.access_token, data.user);

      // Redirect to main compliance dashboard
      router.push("/");
    } catch (err: unknown) {
      const message =
        err instanceof Error
          ? err.message
          : "Failed to connect to authentication server.";
      setErrorMessage(message);
    } finally {
      setIsLoading(false);
    }
  };

  const triggerDemoLogin = async (demoEmail: string) => {
    if (isLoading) return;
    const demoPw = "demo123";
    setEmail(demoEmail);
    setPassword(demoPw);
    setIsLoading(true);
    setErrorMessage(null);

    try {
      const res = await fetch("http://localhost:8000/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: demoEmail,
          password: demoPw,
        }),
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        throw new Error(data.detail || `Demo login failed (${res.status})`);
      }

      login(data.access_token, data.user);
      router.push("/");
    } catch (err: unknown) {
      const message =
        err instanceof Error
          ? err.message
          : "Failed to connect to authentication server.";
      setErrorMessage(message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen w-full grid grid-cols-1 lg:grid-cols-2 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-slate-900 via-[#130d25] to-slate-950 text-white/90 font-sans selection:bg-indigo-500/30 selection:text-white">
      {/* =====================================================================
          1. Left Side (Media & Brand Atmosphere) - Hidden on Mobile
      ===================================================================== */}
      <div className="relative hidden lg:flex flex-col justify-between p-12 lg:p-16 overflow-hidden border-r border-white/10 bg-slate-950/40">
        {/* Background Looping Video Placeholder */}
        <div className="absolute inset-0 z-0 overflow-hidden pointer-events-none">
          <video
            autoPlay
            loop
            muted
            playsInline
            className="object-cover w-full h-full opacity-60 scale-105 filter blur-[1px]"
            poster=""
          >
            <source src="/fintech-ambient.mp4" type="video/mp4" />
          </video>

          {/* Liquid Glass Dynamic Glow Overlays */}
          <div className="absolute inset-0 bg-gradient-to-t from-slate-950 via-slate-950/60 to-transparent" />
          <div className="absolute -top-32 -left-32 w-96 h-96 bg-purple-600/25 rounded-full blur-[140px]" />
          <div className="absolute bottom-10 right-10 w-96 h-96 bg-indigo-600/20 rounded-full blur-[150px]" />
        </div>

        {/* Top Branding */}
        <div className="relative z-10 flex items-center space-x-3.5">
          <div className="h-12 w-12 rounded-2xl bg-white/[0.08] border border-white/15 p-0.5 flex items-center justify-center shadow-[0_8px_32px_0_rgba(0,0,0,0.37)] backdrop-blur-xl">
            <span className="text-2xl">⚖️</span>
          </div>
          <div>
            <span className="font-semibold text-xl tracking-tight text-white/95">
              FinSight
            </span>
            <span className="ml-2.5 text-[11px] px-2.5 py-0.5 rounded-full bg-indigo-500/10 text-indigo-300 border border-indigo-500/20 font-mono">
              Enterprise RegTech
            </span>
          </div>
        </div>

        {/* Center Quote / Pitch */}
        <div className="relative z-10 max-w-lg space-y-6">
          <div className="inline-flex items-center space-x-2 px-3.5 py-1 rounded-full bg-white/5 border border-white/10 text-xs text-indigo-200 backdrop-blur-xl">
            <span>🔒</span>
            <span>Cryptographic Proof of Compliance</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-light tracking-tight text-white/95 leading-snug">
            Autonomous compliance gatekeeper for high-velocity Fintech.
          </h2>
          <p className="text-sm text-white/60 font-light leading-relaxed">
            Cross-reference architectural decisions against the EU AI Act, GDPR, and PSD2 with immutable SHA-256 blockchain ledger audit logging.
          </p>

          <div className="grid grid-cols-2 gap-4 pt-4 border-t border-white/10 text-xs font-light">
            <div className="space-y-1">
              <span className="text-white/40 block text-[10px] uppercase font-sans font-medium">Compliance Assurance</span>
              <span className="text-emerald-300 font-mono text-xs">Zero AI Hallucinations</span>
            </div>
            <div className="space-y-1">
              <span className="text-white/40 block text-[10px] uppercase font-sans font-medium">Audit Ledger</span>
              <span className="text-indigo-300 font-mono text-xs">SHA-256 Hash Chained</span>
            </div>
          </div>
        </div>

        {/* Bottom Metadata */}
        <div className="relative z-10 text-xs text-white/40 font-light flex items-center justify-between">
          <span>&copy; {new Date().getFullYear()} FinSight Technologies.</span>
          <span>B2B Multi-Tenant Platform</span>
        </div>
      </div>

      {/* =====================================================================
          2. Right Side (Centered Glassmorphism Login Form)
      ===================================================================== */}
      <div className="flex items-center justify-center p-6 sm:p-12 relative overflow-hidden">
        {/* Ambient Glows for Mobile & Form Side */}
        <div className="absolute top-1/3 -right-32 w-80 h-80 bg-purple-600/15 rounded-full blur-[140px] pointer-events-none" />
        <div className="absolute -bottom-32 -left-32 w-80 h-80 bg-indigo-600/15 rounded-full blur-[140px] pointer-events-none" />

        <div className="max-w-md w-full relative z-10 space-y-8">
          {/* Mobile Brand Header */}
          <div className="flex lg:hidden items-center space-x-3 justify-center mb-6">
            <div className="h-10 w-10 rounded-2xl bg-white/[0.08] border border-white/15 flex items-center justify-center">
              <span className="text-xl">⚖️</span>
            </div>
            <span className="font-semibold text-lg tracking-tight text-white/95">
              FinSight RegTech
            </span>
          </div>

          {/* Form Card */}
          <div className="bg-white/5 backdrop-blur-2xl border border-white/10 shadow-[0_8px_32px_0_rgba(0,0,0,0.37)] rounded-[2.5rem] p-8 sm:p-10 space-y-6">
            <div className="space-y-2 text-center sm:text-left">
              <h1 className="text-2xl sm:text-3xl font-light tracking-tight text-white/95">
                Sign in to FinSight
              </h1>
              <p className="text-xs sm:text-sm text-white/50 font-light">
                Enter your credentials to access your organization&apos;s compliance portal.
              </p>
            </div>

            {errorMessage && (
              <div className="p-4 rounded-2xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs flex items-center space-x-2 animate-in fade-in duration-200">
                <span>⚠️</span>
                <span>{errorMessage}</span>
              </div>
            )}

            <form onSubmit={handleLogin} className="space-y-4">
              {/* Field 1: Email */}
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-white/70 block">
                  Work Email
                </label>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="admin@nordicpayments.eu"
                  className="w-full bg-black/30 border border-white/10 rounded-2xl px-4 py-3.5 text-sm text-white/90 placeholder-white/30 focus:outline-none focus:border-white/40 focus:ring-1 focus:ring-white/30 backdrop-blur-md transition-all duration-200 ease-out font-light"
                />
              </div>

              {/* Field 2: Password */}
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-white/70 block">
                  Password
                </label>
                <input
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••••••"
                  className="w-full bg-black/30 border border-white/10 rounded-2xl px-4 py-3.5 text-sm text-white/90 placeholder-white/30 focus:outline-none focus:border-white/40 focus:ring-1 focus:ring-white/30 backdrop-blur-md transition-all duration-200 ease-out font-light"
                />
              </div>

              {/* Submit Button */}
              <button
                type="submit"
                disabled={isLoading || !email.trim() || !password}
                className="w-full mt-2 py-3.5 px-6 rounded-2xl bg-white hover:bg-white/90 text-slate-950 font-medium text-sm transition-all duration-200 ease-out disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center space-x-2 active:scale-95 shadow-[0_4px_20px_0_rgba(255,255,255,0.15)]"
              >
                {isLoading ? (
                  <>
                    <span className="inline-block animate-spin">⏳</span>
                    <span>Authenticating...</span>
                  </>
                ) : (
                  <>
                    <span>Sign In</span>
                    <span>&rarr;</span>
                  </>
                )}
              </button>

              {/* Fast-Track Demo Quick Access */}
              <div className="pt-3 space-y-2 border-t border-white/10">
                <div className="flex items-center justify-between text-[10px] text-white/40 uppercase tracking-wider font-mono">
                  <span>Fast-Track Demo Access</span>
                  <span>pw: demo123</span>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <button
                    type="button"
                    onClick={() => triggerDemoLogin("dev@nordicpayments.eu")}
                    disabled={isLoading}
                    className="px-2.5 py-2.5 rounded-xl bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 border border-emerald-500/20 hover:border-emerald-500/35 text-xs font-mono transition-all duration-200 ease-out disabled:opacity-50 disabled:cursor-not-allowed active:scale-95 text-center flex flex-col items-center justify-center space-y-0.5 shadow-sm"
                  >
                    <span className="font-semibold text-[11px]">Demo Developer</span>
                    <span className="text-[9px] text-emerald-400/70 font-sans">No Override</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => triggerDemoLogin("manager@nordicpayments.eu")}
                    disabled={isLoading}
                    className="px-2.5 py-2.5 rounded-xl bg-sky-500/10 hover:bg-sky-500/20 text-sky-300 border border-sky-500/20 hover:border-sky-500/35 text-xs font-mono transition-all duration-200 ease-out disabled:opacity-50 disabled:cursor-not-allowed active:scale-95 text-center flex flex-col items-center justify-center space-y-0.5 shadow-sm"
                  >
                    <span className="font-semibold text-[11px]">Demo Manager</span>
                    <span className="text-[9px] text-sky-400/70 font-sans">Full Override</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => triggerDemoLogin("admin@nordicpayments.eu")}
                    disabled={isLoading}
                    className="px-2.5 py-2.5 rounded-xl bg-purple-500/10 hover:bg-purple-500/20 text-purple-300 border border-purple-500/20 hover:border-purple-500/35 text-xs font-mono transition-all duration-200 ease-out disabled:opacity-50 disabled:cursor-not-allowed active:scale-95 text-center flex flex-col items-center justify-center space-y-0.5 shadow-sm"
                  >
                    <span className="font-semibold text-[11px]">Demo Admin</span>
                    <span className="text-[9px] text-purple-400/70 font-sans">Team Mgmt</span>
                  </button>
                </div>
              </div>
            </form>

            {/* Link to Register Org */}
            <div className="pt-4 border-t border-white/10 text-center">
              <p className="text-xs text-white/50 font-light">
                Need to onboard a new organization?{" "}
                <Link
                  href="/register"
                  className="text-indigo-300 hover:text-indigo-200 font-medium underline underline-offset-4 transition-colors duration-200"
                >
                  Register Organization
                </Link>
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
