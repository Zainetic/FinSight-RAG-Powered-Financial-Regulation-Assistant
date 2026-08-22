"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "../context/AuthContext";

export default function RegisterPage() {
  const [orgName, setOrgName] = useState("");
  const [adminEmail, setAdminEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const { login } = useAuth();
  const router = useRouter();

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!orgName.trim() || !adminEmail.trim() || !password) return;

    if (password !== confirmPassword) {
      setErrorMessage("Passwords do not match.");
      return;
    }

    if (password.length < 8) {
      setErrorMessage("Password must be at least 8 characters long.");
      return;
    }

    setIsLoading(true);
    setErrorMessage(null);

    try {
      const res = await fetch("http://localhost:8000/api/v1/auth/register-org", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          org_name: orgName.trim(),
          admin_email: adminEmail.trim(),
          password,
        }),
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        throw new Error(data.detail || `Registration failed (${res.status})`);
      }

      // Save token & user to Auth Context
      login(data.access_token, {
        id: data.user.id,
        email: data.user.email,
        role: data.user.role,
        org_id: data.organization.id,
        org_name: data.organization.name,
      });

      // Redirect to main compliance dashboard
      router.push("/");
    } catch (err: unknown) {
      const message =
        err instanceof Error
          ? err.message
          : "Failed to connect to registration service.";
      setErrorMessage(message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen w-full flex items-center justify-center p-6 sm:p-12 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-slate-900 via-[#130d25] to-slate-950 text-white/90 font-sans selection:bg-indigo-500/30 selection:text-white relative overflow-hidden">
      {/* Ambient Glassmorphism Gradient Glow Orbs */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden z-0">
        <div className="absolute -top-48 -right-48 w-[650px] h-[650px] bg-purple-600/15 rounded-full blur-[150px]" />
        <div className="absolute top-1/2 -left-48 w-[600px] h-[600px] bg-indigo-600/15 rounded-full blur-[140px]" />
      </div>

      <div className="max-w-md w-full relative z-10 space-y-8">
        {/* Brand Header */}
        <div className="flex items-center space-x-3 justify-center">
          <div className="h-11 w-11 rounded-2xl bg-white/[0.08] border border-white/15 p-0.5 flex items-center justify-center shadow-[0_8px_32px_0_rgba(0,0,0,0.37)] backdrop-blur-xl">
            <span className="text-xl">⚖️</span>
          </div>
          <div>
            <span className="font-semibold text-lg tracking-tight text-white/95">
              FinSight
            </span>
            <span className="ml-2 text-[10px] px-2 py-0.5 rounded-full bg-purple-500/10 text-purple-300 border border-purple-500/20 font-mono">
              B2B Onboarding
            </span>
          </div>
        </div>

        {/* Card */}
        <div className="bg-white/5 backdrop-blur-2xl border border-white/10 shadow-[0_8px_32px_0_rgba(0,0,0,0.37)] rounded-[2.5rem] p-8 sm:p-10 space-y-6">
          <div className="space-y-2 text-center sm:text-left">
            <h1 className="text-2xl sm:text-3xl font-light tracking-tight text-white/95">
              Register Organization
            </h1>
            <p className="text-xs sm:text-sm text-white/50 font-light leading-relaxed">
              Create a dedicated tenant environment and generate your organization&apos;s cryptographic Genesis Block.
            </p>
          </div>

          {errorMessage && (
            <div className="p-4 rounded-2xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs flex items-center space-x-2">
              <span>⚠️</span>
              <span>{errorMessage}</span>
            </div>
          )}

          <form onSubmit={handleRegister} className="space-y-4">
            {/* Field 1: Organization Name */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-white/70 block">
                Organization / Company Name
              </label>
              <input
                type="text"
                required
                value={orgName}
                onChange={(e) => setOrgName(e.target.value)}
                placeholder="Acme Payments Europe"
                className="w-full bg-black/30 border border-white/10 rounded-2xl px-4 py-3 text-sm text-white/90 placeholder-white/30 focus:outline-none focus:border-indigo-500/50 focus:ring-1 focus:ring-indigo-500/50 backdrop-blur-md transition-all font-light"
              />
            </div>

            {/* Field 2: Master Admin Email */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-white/70 block">
                Master Admin Email
              </label>
              <input
                type="email"
                required
                value={adminEmail}
                onChange={(e) => setAdminEmail(e.target.value)}
                placeholder="admin@acmepayments.com"
                className="w-full bg-black/30 border border-white/10 rounded-2xl px-4 py-3 text-sm text-white/90 placeholder-white/30 focus:outline-none focus:border-indigo-500/50 focus:ring-1 focus:ring-indigo-500/50 backdrop-blur-md transition-all font-light"
              />
            </div>

            {/* Field 3: Password */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-white/70 block">
                Master Admin Password
              </label>
              <input
                type="password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Minimum 8 characters"
                className="w-full bg-black/30 border border-white/10 rounded-2xl px-4 py-3 text-sm text-white/90 placeholder-white/30 focus:outline-none focus:border-indigo-500/50 focus:ring-1 focus:ring-indigo-500/50 backdrop-blur-md transition-all font-light"
              />
            </div>

            {/* Field 4: Confirm Password */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-white/70 block">
                Confirm Password
              </label>
              <input
                type="password"
                required
                minLength={8}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Re-enter password"
                className="w-full bg-black/30 border border-white/10 rounded-2xl px-4 py-3 text-sm text-white/90 placeholder-white/30 focus:outline-none focus:border-indigo-500/50 focus:ring-1 focus:ring-indigo-500/50 backdrop-blur-md transition-all font-light"
              />
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={isLoading || !orgName.trim() || !adminEmail.trim() || !password}
              className="w-full mt-2 py-3.5 px-6 rounded-2xl bg-white hover:bg-white/90 text-slate-950 font-medium text-sm transition-all disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center space-x-2 active:scale-[0.98] shadow-[0_4px_20px_0_rgba(255,255,255,0.15)]"
            >
              {isLoading ? (
                <span>Generating Genesis Block & Account...</span>
              ) : (
                <>
                  <span>Initialize Organization</span>
                  <span>&rarr;</span>
                </>
              )}
            </button>
          </form>

          {/* Link to Login */}
          <div className="pt-4 border-t border-white/10 text-center">
            <p className="text-xs text-white/50 font-light">
              Already registered?{" "}
              <Link
                href="/login"
                className="text-indigo-300 hover:text-indigo-200 font-medium underline underline-offset-4 transition-colors"
              >
                Sign In to Existing Org
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
