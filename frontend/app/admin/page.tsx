"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "../context/AuthContext";

interface TeamMember {
  id: string;
  org_id: string;
  email: string;
  role: "DEVELOPER" | "MANAGER" | "MASTER_ADMIN";
  created_at: string;
}

export default function AdminPage() {
  const { user, token, isAuthenticated, isLoading: isAuthLoading, logout } = useAuth();
  const router = useRouter();

  // Team State
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [isLoadingMembers, setIsLoadingMembers] = useState(true);

  // New User Form State
  const [newUserEmail, setNewUserEmail] = useState("");
  const [newUserPassword, setNewUserPassword] = useState("");
  const [newUserRole, setNewUserRole] = useState<"DEVELOPER" | "MANAGER">("DEVELOPER");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  // Auth Guard
  useEffect(() => {
    if (!isAuthLoading) {
      if (!isAuthenticated) {
        router.push("/login");
      }
    }
  }, [isAuthenticated, isAuthLoading, router]);

  // Fetch Team Members
  const fetchTeamMembers = async () => {
    if (!token) return;
    setIsLoadingMembers(true);
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const res = await fetch(`${apiUrl}/api/v1/auth/users`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (res.ok) {
        const data = await res.json();
        setMembers(data.users || []);
      }
    } catch (e) {
      console.error("Failed to load team members:", e);
    } finally {
      setIsLoadingMembers(false);
    }
  };

  useEffect(() => {
    if (token && user?.role === "MASTER_ADMIN") {
      fetchTeamMembers();
    }
  }, [token, user]);

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newUserEmail.trim() || !newUserPassword || !token) return;

    setIsSubmitting(true);
    setFormError(null);
    setFormSuccess(null);

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const res = await fetch(`${apiUrl}/api/v1/auth/create-user`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          email: newUserEmail.trim(),
          password: newUserPassword,
          role: newUserRole,
        }),
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        throw new Error(data.detail || `Failed to create user (${res.status})`);
      }

      setFormSuccess(`User ${newUserEmail} successfully provisioned as ${newUserRole}.`);
      setNewUserEmail("");
      setNewUserPassword("");
      fetchTeamMembers();
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Failed to create user.";
      setFormError(message);
    } finally {
      setIsSubmitting(false);
    }
  };


  const formatTimestamp = (raw: string): string => {
    try {
      const d = new Date(raw);
      return new Intl.DateTimeFormat("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      }).format(d);
    } catch {
      return raw;
    }
  };

  if (isAuthLoading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center text-white/50 font-light text-sm">
        Verifying cryptographic session credentials...
      </div>
    );
  }

  if (user?.role !== "MASTER_ADMIN") {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center p-6 text-white/90">
        <div className="max-w-md w-full bg-white/5 border border-white/10 rounded-3xl p-8 backdrop-blur-2xl text-center space-y-4 shadow-2xl">
          <div className="text-4xl">🚫</div>
          <h2 className="text-2xl font-light text-rose-300">Access Restricted</h2>
          <p className="text-sm text-white/60 font-light">
            This administration panel requires the <strong>MASTER_ADMIN</strong> role. Your account is assigned role <strong>{user?.role}</strong>.
          </p>
          <Link
            href="/"
            className="inline-block mt-4 px-6 py-2.5 rounded-xl bg-white/10 hover:bg-white/20 text-white text-sm font-medium border border-white/10 transition-all duration-200 ease-out active:scale-95"
          >
            &larr; Return to Compliance Dashboard
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-slate-900 via-[#150e28] to-slate-950 text-white/90 relative overflow-x-hidden selection:bg-indigo-500/30 selection:text-white flex flex-col font-sans">
      {/* Ambient Glassmorphism Gradient Glow Orbs */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden z-0">
        <div className="absolute -top-48 -right-48 w-[700px] h-[700px] bg-purple-600/15 rounded-full blur-[150px] animate-pulse" />
        <div className="absolute top-1/2 -left-48 w-[600px] h-[600px] bg-indigo-600/15 rounded-full blur-[140px]" />
      </div>

      {/* Header */}
      <header className="border-b border-white/10 bg-white/[0.02] backdrop-blur-2xl sticky top-0 z-40 transition-all duration-200">
        <div className="max-w-6xl mx-auto px-6 sm:px-8 h-20 flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <Link
              href="/"
              className="h-10 w-10 rounded-2xl bg-white/[0.08] border border-white/15 flex items-center justify-center text-lg hover:bg-white/15 transition-all duration-200 ease-out active:scale-95"
              title="Return to Dashboard"
            >
              <span>&larr;</span>
            </Link>
            <div>
              <div className="flex items-center space-x-2.5">
                <span className="font-semibold text-lg tracking-tight text-white/95">
                  FinSight Admin
                </span>
                <span className="text-[11px] px-2.5 py-0.5 rounded-full bg-purple-500/15 text-purple-300 border border-purple-500/25 font-mono">
                  MASTER_ADMIN
                </span>
              </div>
              <p className="text-xs text-white/50 font-light">
                {user?.org_name || "Enterprise"} Organization Control Center
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-3">
            <Link
              href="/"
              className="text-xs px-4 py-2 rounded-xl bg-white/[0.06] hover:bg-white/[0.12] text-white/80 hover:text-white border border-white/15 backdrop-blur-xl transition-all duration-200 ease-out active:scale-95"
            >
              Compliance Engine
            </Link>
            <button
              onClick={logout}
              className="text-xs px-4 py-2 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/20 backdrop-blur-xl transition-all duration-200 ease-out active:scale-95"
            >
              Sign Out
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-5xl mx-auto px-6 sm:px-8 py-12 flex-1 w-full space-y-10 relative z-10">
        {/* Title */}
        <section className="space-y-2">
          <h1 className="text-3xl sm:text-4xl font-light tracking-tight text-white/95">
            Team & Role-Based Access Control
          </h1>
          <p className="text-sm text-white/60 font-light max-w-2xl leading-relaxed">
            Provision user accounts for developers and compliance managers under your organization. Developers are restricted from executing manual compliance overrides.
          </p>
        </section>

        {/* Top: User Creation Form with Perfectly Aligned Flex Header & Action Button */}
        <section className="bg-white/5 backdrop-blur-2xl border border-white/10 shadow-[0_8px_32px_0_rgba(0,0,0,0.37)] rounded-[2.5rem] p-8 sm:p-10 space-y-6">
          <div className="flex items-center justify-between w-full border-b border-white/5 pb-4">
            <div className="flex items-center space-x-3">
              <span className="text-2xl">➕</span>
              <h2 className="text-xl sm:text-2xl font-light text-white/95 tracking-tight">
                Provision Organization User
              </h2>
            </div>
            <span className="text-xs text-white/40 font-mono">
              Tenant ID: {user?.org_id?.slice(0, 8)}...
            </span>
          </div>

          {formSuccess && (
            <div className="p-4 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 text-xs flex items-center space-x-2 animate-in fade-in duration-200">
              <span>✅</span>
              <span>{formSuccess}</span>
            </div>
          )}

          {formError && (
            <div className="p-4 rounded-2xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs flex items-center space-x-2 animate-in fade-in duration-200">
              <span>⚠️</span>
              <span>{formError}</span>
            </div>
          )}

          <form onSubmit={handleCreateUser} className="space-y-5">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              {/* Field 1: Email */}
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-white/70 block">
                  User Email
                </label>
                <input
                  type="email"
                  required
                  value={newUserEmail}
                  onChange={(e) => setNewUserEmail(e.target.value)}
                  placeholder="developer@company.com"
                  className="w-full bg-black/30 border border-white/10 rounded-2xl px-4 py-3.5 text-xs sm:text-sm text-white/90 placeholder-white/30 focus:outline-none focus:border-white/40 focus:ring-1 focus:ring-white/30 backdrop-blur-md font-light transition-all duration-200 ease-out"
                />
              </div>

              {/* Field 2: Password */}
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-white/70 block">
                  Initial Password
                </label>
                <input
                  type="password"
                  required
                  minLength={8}
                  value={newUserPassword}
                  onChange={(e) => setNewUserPassword(e.target.value)}
                  placeholder="Minimum 8 characters"
                  className="w-full bg-black/30 border border-white/10 rounded-2xl px-4 py-3.5 text-xs sm:text-sm text-white/90 placeholder-white/30 focus:outline-none focus:border-white/40 focus:ring-1 focus:ring-white/30 backdrop-blur-md font-light transition-all duration-200 ease-out"
                />
              </div>

              {/* Field 3: Role Assignment */}
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-white/70 block">
                  RBAC Role Assignment
                </label>
                <select
                  value={newUserRole}
                  onChange={(e) => setNewUserRole(e.target.value as "DEVELOPER" | "MANAGER")}
                  className="w-full bg-black/30 border border-white/10 rounded-2xl px-4 py-3.5 text-xs sm:text-sm text-white/90 focus:outline-none focus:border-white/40 focus:ring-1 focus:ring-white/30 backdrop-blur-md font-light transition-all duration-200 ease-out"
                >
                  <option value="DEVELOPER" className="bg-slate-900 text-white">
                    DEVELOPER (Read / Evaluate)
                  </option>
                  <option value="MANAGER" className="bg-slate-900 text-white">
                    MANAGER (Full Override)
                  </option>
                </select>
              </div>
            </div>

            {/* Bottom Form Action Bar: Vertically Centered Flexbox Alignment */}
            <div className="flex flex-col sm:flex-row items-center justify-between w-full gap-3 pt-2">
              <p className="text-xs text-white/40 font-light text-center sm:text-left">
                User will immediately receive credentials to run compliance evaluations under this tenant.
              </p>
              <button
                type="submit"
                disabled={isSubmitting || !newUserEmail.trim() || !newUserPassword}
                className="w-full sm:w-auto px-7 py-3.5 rounded-2xl bg-white hover:bg-white/90 text-slate-950 font-medium text-xs sm:text-sm transition-all duration-200 ease-out disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center space-x-2 active:scale-95 shadow-[0_4px_20px_0_rgba(255,255,255,0.15)] whitespace-nowrap"
              >
                {isSubmitting ? (
                  <>
                    <span className="inline-block animate-spin">⏳</span>
                    <span>Provisioning Account...</span>
                  </>
                ) : (
                  <>
                    <span>➕</span>
                    <span>Add User</span>
                  </>
                )}
              </button>
            </div>
          </form>
        </section>

        {/* Bottom: Team Members Directory */}
        <section className="bg-white/5 backdrop-blur-2xl border border-white/10 shadow-[0_8px_32px_0_rgba(0,0,0,0.37)] rounded-[2.5rem] p-8 sm:p-10 space-y-6">
          <div className="flex items-center justify-between w-full border-b border-white/5 pb-4">
            <div className="flex items-center space-x-3">
              <span className="text-2xl">👥</span>
              <h2 className="text-xl sm:text-2xl font-light text-white/95 tracking-tight">
                Organization Team Members ({members.length})
              </h2>
            </div>
            <button
              onClick={fetchTeamMembers}
              className="text-xs text-white/70 hover:text-white px-3.5 py-2 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 transition-all duration-200 ease-out font-mono active:scale-95"
            >
              ↻ Refresh List
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs sm:text-sm font-light">
              <thead>
                <tr className="border-b border-white/10 text-white/40 text-[11px] uppercase tracking-wider font-medium">
                  <th className="pb-3 px-4">Member Email</th>
                  <th className="pb-3 px-4">RBAC Role</th>
                  <th className="pb-3 px-4">Permissions</th>
                  <th className="pb-3 px-4">Joined Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5 font-mono text-xs">
                {isLoadingMembers ? (
                  <tr>
                    <td colSpan={4} className="py-8 text-center text-white/40 font-sans">
                      Loading team members...
                    </td>
                  </tr>
                ) : members.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="py-8 text-center text-white/40 font-sans">
                      No additional members found.
                    </td>
                  </tr>
                ) : (
                  members.map((m) => (
                    <tr key={m.id} className="hover:bg-white/[0.04] transition-colors duration-200">
                      <td className="py-4 px-4 font-sans text-white/90">
                        {m.email}
                        {m.id === user?.id && (
                          <span className="ml-2 text-[10px] px-2 py-0.5 rounded-full bg-white/10 text-white/70 border border-white/10 font-mono">
                            You
                          </span>
                        )}
                      </td>
                      <td className="py-4 px-4">
                        {m.role === "MASTER_ADMIN" && (
                          <span className="px-2.5 py-1 rounded-full bg-purple-500/15 text-purple-300 border border-purple-500/25 text-[11px]">
                            MASTER_ADMIN
                          </span>
                        )}
                        {m.role === "MANAGER" && (
                          <span className="px-2.5 py-1 rounded-full bg-sky-500/15 text-sky-300 border border-sky-500/25 text-[11px]">
                            MANAGER
                          </span>
                        )}
                        {m.role === "DEVELOPER" && (
                          <span className="px-2.5 py-1 rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/25 text-[11px]">
                            DEVELOPER
                          </span>
                        )}
                      </td>
                      <td className="py-4 px-4 font-sans text-white/60 text-xs">
                        {m.role === "DEVELOPER"
                          ? "Run Compliance Audits (No Override)"
                          : m.role === "MANAGER"
                          ? "Run Audits & Human Overrides"
                          : "Full Admin, User Mgmt & Overrides"}
                      </td>
                      <td className="py-4 px-4 text-white/40">
                        {formatTimestamp(m.created_at)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>
      </main>
    </div>
  );
}
