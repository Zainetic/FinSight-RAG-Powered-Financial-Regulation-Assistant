# ⚖️ FinSight — AI-Powered RegTech Compliance Gatekeeper

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Next.js 16](https://img.shields.io/badge/Frontend-Next.js%2016-000000?style=flat&logo=next.js&logoColor=white)](https://nextjs.org)
[![Multi-Tenancy](https://img.shields.io/badge/Architecture-B2B%20Multi--Tenant-blueviolet?style=flat)](#-multi-tenancy--rbac-architecture)
[![JWT & RBAC](https://img.shields.io/badge/Security-JWT%20%2B%20RBAC-success?style=flat)](#-rbac-permission-matrix)
[![LangChain](https://img.shields.io/badge/AI-LangChain%20RAG-1C3C3C?style=flat&logo=langchain&logoColor=white)](https://python.langchain.com)
[![Google Gemini](https://img.shields.io/badge/LLM-Gemini%20Flash-4285F4?style=flat&logo=google&logoColor=white)](https://aistudio.google.com)
[![PostgreSQL](https://img.shields.io/badge/Ledger-PostgreSQL%2016-4169E1?style=flat&logo=postgresql&logoColor=white)](https://www.postgresql.org)
[![Docker](https://img.shields.io/badge/Deployment-Docker%20Compose-2496ED?style=flat&logo=docker&logoColor=white)](https://www.docker.com)
[![License: Proprietary](https://img.shields.io/badge/License-Proprietary-red.svg)](#-license--copyright)

**FinSight** is an enterprise-grade Regulatory Technology (RegTech) platform and automated compliance gatekeeper built for B2B fintech ecosystems. It cross-references fintech software architectures, data flows, and machine learning deployments against regional regulatory frameworks (**EU AI Act 2024/1689**, **GDPR 2016/679**, **PSD2 2015/2366**, **UK DPA 2018**, and **US CCPA/CPRA**), sealing every audit determination into an immutable, cryptographic SHA-256 PostgreSQL ledger with multi-tenant row-level isolation and Role-Based Access Control (RBAC).

---

## 🏛️ Key Capabilities

* **🏢 B2B Multi-Tenancy & Genesis Blocks**: Complete tenant isolation for enterprise clients. Each registered organization is automatically provisioned with a cryptographic **Genesis Block (`#0`)** from which all subsequent compliance hashes chain deterministically.
* **🛡️ Role-Based Access Control (RBAC) & JWT Security**: High-security token authentication (`HS256`, `bcrypt`) with three strict permission tiers: `MASTER_ADMIN`, `MANAGER`, and `DEVELOPER`.
* **⚡ Real-Time SSE Streaming**: Token-by-token streaming of executive legal analyses via Server-Sent Events (SSE), delivering immediate Time-To-First-Token (TTFT).
* **🎯 Multi-Jurisdictional FAISS RAG**: Semantic vector retrieval with metadata filtering (`jurisdictions: ["EU", "UK", "US"]`) ensuring cross-regional legal accuracy.
* **🔒 Tenant-Isolated SHA-256 Ledger**: Every compliance assessment is cryptographically linked to the previous transaction hash (`prev_hash`) within the organization's hash chain using deterministic canonical serialization.
* **🧑‍⚖️ Human-in-the-Loop Dispute Protocol**: Compliance managers and admins can dispute high-risk determinations by appending an immutable override block (`OVERRIDDEN_BY_HUMAN`) without breaking hash-chain continuity. Developers are strictly blocked from overrides.
* **🚀 DevSecOps CI/CD Gatekeeper Webhook**: Dedicated `POST /api/v1/scan-repo` endpoint for GitHub Actions that returns HTTP 200 for compliant architectures and HTTP 403 to block non-compliant PR merges.
* **✨ Apple "Liquid Glass" Next.js UI**: Modern dark-mode interface featuring 50/50 split-screen login, organization onboarding, admin team provisioning, and conditional UI rendering that hides dispute triggers for developer roles.

---

## 🔐 RBAC Permission Matrix

| Operation / Capability | Endpoint | `MASTER_ADMIN` | `MANAGER` | `DEVELOPER` |
| :--- | :--- | :---: | :---: | :---: |
| **Register New Organization & Genesis Block** | `POST /api/v1/auth/register-org` | ✅ | ❌ | ❌ |
| **Provision Team Users (`DEV`/`MGR`)** | `POST /api/v1/auth/create-user` | ✅ | ❌ | ❌ |
| **Access Admin Team Management (`/admin`)** | Next.js `/admin` Route | ✅ | ❌ | ❌ |
| **View Organization Members** | `GET /api/v1/auth/users` | ✅ | ✅ | ❌ |
| **Run Streaming Compliance Audits** | `POST /api/v1/evaluate` | ✅ | ✅ | ✅ |
| **View Tenant Cryptographic Ledger** | `GET /api/v1/ledger` | ✅ | ✅ | ✅ |
| **Execute Human-in-the-Loop Override** | `POST /api/v1/override` | ✅ | ✅ | 🚫 *(HTTP 403 / Hidden in UI)* |
| **CI/CD Repository Scan Webhook** | `POST /api/v1/scan-repo` | ✅ | ✅ | ✅ |

---

## 🏗️ Architecture & Multi-Tenant Data Flow

```mermaid
flowchart TD
    subgraph ClientLayer["🖥️ Frontend (Next.js 16 App Router) & CI/CD"]
        AUTH_CTX["AuthContext & LocalStorage Session"]
        LOGIN_UI["Split-Screen Login (/login)"]
        REG_UI["Organization Onboarding (/register)"]
        ADMIN_UI["Admin Team Management (/admin)"]
        DASH_UI["Compliance Dashboard (/) [RBAC Conditional UI]"]
        GHA["GitHub Actions CI/CD Pipeline"]
    end

    subgraph AuthLayer["🔑 Authentication & RBAC Middleware"]
        JWT_GUARD["FastAPI get_current_user Dependency"]
        ROLE_GUARD["RBAC require_roles Validator"]
    end

    subgraph APILayer["⚡ FastAPI Gateway"]
        AUTH_EP["POST /api/v1/auth (login, register-org, create-user, users)"]
        EVAL_EP["POST /api/v1/evaluate (SSE Streaming)"]
        SCAN_EP["POST /api/v1/scan-repo (CI/CD Webhook)"]
        OVER_EP["POST /api/v1/override (Dispute Override)"]
        LEDG_EP["GET /api/v1/ledger (Ledger Explorer)"]
    end

    subgraph RAGLayer["🧠 LangChain & Vector Engine"]
        FAISS[("FAISS Vector Index\n(EUR-Lex, GDPR, AI Act, PSD2)")]
        PROMPT["Strict 3-Tier Markdown Prompt"]
        LLM["Google Gemini Flash LLM (astream)"]
        HYDRATE["Context Citation Hydration Engine"]
    end

    subgraph LedgerLayer["🔒 PostgreSQL Multi-Tenant Ledger"]
        ORGS[("organizations Table")]
        USERS[("users Table (Bcrypt Hashed)")]
        GENESIS["Genesis Block Generator (#0)"]
        HASH["Deterministic SHA-256 Canonical Hasher"]
        CHAIN[("compliance_ledger Table\n(org_id Scoped prev_hash -> tx_hash)")]
    end

    LOGIN_UI -->|Authenticate| AUTH_EP
    REG_UI -->|Register Org & Admin| AUTH_EP
    ADMIN_UI -->|Bearer JWT| AUTH_EP
    DASH_UI -->|Bearer JWT + Stream Query| EVAL_EP
    DASH_UI -->|Bearer JWT + Dispute| OVER_EP
    DASH_UI -->|Bearer JWT + History| LEDG_EP
    GHA -->|Audit Diff| SCAN_EP

    AUTH_EP --> ORGS
    AUTH_EP --> USERS
    AUTH_EP --> GENESIS
    GENESIS --> CHAIN

    EVAL_EP --> JWT_GUARD
    OVER_EP --> JWT_GUARD
    OVER_EP --> ROLE_GUARD
    LEDG_EP --> JWT_GUARD
    SCAN_EP --> JWT_GUARD

    JWT_GUARD --> EVAL_EP
    EVAL_EP --> FAISS
    SCAN_EP --> FAISS
    FAISS --> HYDRATE
    HYDRATE --> PROMPT
    PROMPT --> LLM

    LLM -->|SSE Streaming Tokens| DASH_UI
    LLM --> HASH
    OVER_EP --> HASH
    SCAN_EP --> HASH
    HASH --> CHAIN
```

---

## 📂 Monorepo Structure

```text
FinSight/
├── .github/
│   └── workflows/
│       └── compliance-gate.yml      # GitHub Actions automated PR compliance gate
├── backend/
│   ├── data/
│   │   ├── faiss_index/             # Pre-built FAISS vector index (index.faiss, index.pkl)
│   │   └── raw_pdfs/                # EU AI Act, GDPR, and PSD2 source regulations
│   ├── src/
│   │   ├── api/
│   │   │   ├── auth.py              # Auth endpoints (/register-org, /login, /create-user, /users)
│   │   │   ├── main.py              # FastAPI app definition, CORS, router mounting
│   │   │   └── routes.py            # Protected SSE evaluation, dispute override, and CI/CD routes
│   │   ├── core/
│   │   │   ├── auth.py              # Bcrypt hashing, JWT generation/decoding, RBAC dependencies
│   │   │   ├── database.py          # PostgreSQL multi-tenant DDL (organizations, users, ledger)
│   │   │   ├── ledger.py            # Deterministic multi-tenant SHA-256 hash chaining & Genesis block
│   │   │   ├── llm.py               # Singleton Gemini Flash LLM client
│   │   │   └── rag.py               # Asynchronous streaming RAG & context hydration
│   │   └── ingestion/
│   │       └── build_index.py       # PDF ingestion & FAISS embedding generation script
│   ├── test_multitenancy_rbac.py    # Integration test suite for Auth, RBAC, and Ledger isolation
│   ├── Dockerfile                   # Python 3.13 + CPU-only PyTorch container
│   └── requirements.txt             # Backend dependencies (passlib, bcrypt, PyJWT, email-validator)
├── frontend/
│   ├── app/
│   │   ├── admin/
│   │   │   └── page.tsx             # Protected Admin Team Management & user provisioning
│   │   ├── context/
│   │   │   └── AuthContext.tsx      # React AuthContext & persistent localStorage JWT store
│   │   ├── login/
│   │   │   └── page.tsx             # 50/50 Split-Screen Login UI with video placeholder
│   │   ├── register/
│   │   │   └── page.tsx             # Organization Onboarding & Genesis Block registration
│   │   ├── globals.css              # Tailwind CSS imports and typography plugins
│   │   ├── layout.tsx               # Root Next.js layout wrapped in AuthProvider
│   │   └── page.tsx                 # Compliance dashboard with RBAC conditional rendering
│   ├── Dockerfile                   # Node.js 20 container definition
│   ├── package.json                 # Next.js 16, React 19, ReactMarkdown dependencies
│   └── tsconfig.json                # Strict TypeScript configuration
├── .env.example                     # Environment configuration template
├── .gitignore                       # Production git ignore configuration
├── LICENSE                          # Proprietary and confidential license
└── docker-compose.yml               # Multi-container orchestration (DB with healthcheck, API, Frontend)
```

---

## 🚀 Quickstart Guide

### Prerequisites

* [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Docker Compose v2+)
* [Google Gemini API Key](https://aistudio.google.com/)

---

### Option 1: One-Click Launch with Docker Compose (Recommended)

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/your-username/FinSight.git
   cd FinSight
   ```

2. **Configure Environment Variables**:
   Create a `.env` file in the root workspace:
   ```bash
   cp .env.example .env
   ```
   Configure your environment variables:
   ```env
   GOOGLE_API_KEY=your_actual_gemini_api_key
   GEMINI_MODEL=gemini-3.6-flash
   JWT_SECRET_KEY=your-super-secure-cryptographic-jwt-secret-key-2026
   POSTGRES_DB=finsight_db
   POSTGRES_USER=postgres
   POSTGRES_PASSWORD=postgres
   POSTGRES_HOST=db
   POSTGRES_PORT=5432
   NEXT_PUBLIC_API_URL=http://localhost:8000
   ```

3. **Start All Services**:
   ```bash
   docker compose up --build
   ```

4. **Access the Applications**:
   * 🖥️ **Compliance Portal**: [http://localhost:3000](http://localhost:3000) *(Redirects to `/login`)*
   * 🏢 **Register New Organization**: [http://localhost:3000/register](http://localhost:3000/register)
   * ⚡ **FastAPI Interactive Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
   * 🗄️ **PostgreSQL Database**: `localhost:5432`

---

### Option 2: Local Development Setup (Manual)

#### 1. Start PostgreSQL
```bash
docker run -d --name finsight_postgres \
  -e POSTGRES_DB=finsight_db \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 postgres:16-alpine
```

#### 2. Start the FastAPI Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies (CPU-only PyTorch first)
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt

# Run integration test suite
python test_multitenancy_rbac.py

# Start backend server
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
```

#### 3. Start the Next.js Frontend
```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## 📡 RESTful API Reference

All protected endpoints require the HTTP header: `Authorization: Bearer <JWT_TOKEN>`.

### 1. Authentication Endpoints

#### `POST /api/v1/auth/register-org` — Register Organization & Genesis Block
Registers a new enterprise client, creates a `MASTER_ADMIN` user, and commits the initial Genesis Block (`#0`, `prev_hash = "0"*64`) for that organization.
* **Request Body**:
  ```json
  {
    "org_name": "Nordic Payments AB",
    "admin_email": "admin@nordicpayments.se",
    "password": "SecureAdminPassword2026!"
  }
  ```
* **Response (HTTP 201)**:
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6...",
    "token_type": "bearer",
    "expires_in": 86400,
    "user": { "id": "fa8f2cbc...", "email": "admin@nordicpayments.se", "role": "MASTER_ADMIN", "org_id": "9a1b2c..." },
    "organization": { "id": "9a1b2c...", "name": "Nordic Payments AB" },
    "genesis_block": { "tx_hash": "2e0bb537...", "prev_hash": "0000000000000000000000000000000000000000000000000000000000000000" }
  }
  ```

#### `POST /api/v1/auth/login` — User Authentication
Authenticates credentials against stored `bcrypt` password hashes and returns a signed JWT.
* **Request Body**:
  ```json
  {
    "email": "admin@nordicpayments.se",
    "password": "SecureAdminPassword2026!"
  }
  ```

#### `POST /api/v1/auth/create-user` — Provision Team Member (`MASTER_ADMIN` only)
Allows a Master Admin to create `DEVELOPER` or `MANAGER` accounts under their organization.
* **Request Body**:
  ```json
  {
    "email": "developer@nordicpayments.se",
    "password": "DeveloperPassword2026!",
    "role": "DEVELOPER"
  }
  ```

---

### 2. RegTech Compliance Endpoints

#### `POST /api/v1/evaluate` — Stream Compliance Assessment (SSE)
Executes real-time RAG evaluation against the FAISS vector database and commits the resulting assessment to the tenant's PostgreSQL ledger.
* **Headers**: `Authorization: Bearer <token>`
* **Request Body**:
  ```json
  {
    "query": "We are developing a cloud-hosted biometric facial recognition gateway to categorize retail banking users and authorize high-value payments automatically.",
    "jurisdictions": ["EU (AI Act, GDPR, PSD2)"]
  }
  ```
* **Response**: `text/event-stream` delivering incremental tokens:
  ```text
  data: {"type": "start", "jurisdictions": ["EU (AI Act, GDPR, PSD2)"], "citations": [...]}

  data: {"type": "token", "content": "### 🚨 Risk Classification\n* **EU AI Act**: Prohibited..."}

  data: {"type": "done", "audit_id": "7b8f9e...", "tx_hash": "a1b2c3...", "prev_hash": "2e0bb5...", "is_compliant": false}
  ```

---

#### `POST /api/v1/override` — Human-in-the-Loop Dispute (`MANAGER` & `MASTER_ADMIN`)
Appends an immutable dispute block linked to the latest `tx_hash` in the tenant's chain. Returns **HTTP 403 Forbidden** if invoked by a `DEVELOPER`.
* **Headers**: `Authorization: Bearer <token>`
* **Request Body**:
  ```json
  {
    "audit_id": "7b8f9e...",
    "justification": "Biometric processing is strictly localized on-device with zero cloud telemetry under GDPR Art. 9(2)(a) explicit consent."
  }
  ```
* **Response (HTTP 200)**:
  ```json
  {
    "audit_id": "8c9a1b...",
    "original_audit_id": "7b8f9e...",
    "org_id": "9a1b2c...",
    "status": "OVERRIDDEN_BY_HUMAN",
    "prev_hash": "a1b2c3...",
    "tx_hash": "d4e5f6...",
    "timestamp": "2026-08-22T02:00:00Z"
  }
  ```

---

#### `GET /api/v1/ledger` — Inspect Tenant Ledger & Verify Integrity
Fetches the 10 most recent blocks for the caller's organization and executes a full cryptographic verification of the organization's hash chain.
* **Headers**: `Authorization: Bearer <token>`
* **Response (HTTP 200)**:
  ```json
  {
    "org_id": "9a1b2c...",
    "total": 10,
    "chain_valid": true,
    "total_blocks_verified": 10,
    "verification_error": null,
    "blocks": [
      {
        "audit_id": "8c9a1b...",
        "user_query": "...",
        "prev_hash": "a1b2c3...",
        "tx_hash": "d4e5f6...",
        "timestamp": "2026-08-22T02:00:00Z"
      }
    ]
  }
  ```

---

#### `POST /api/v1/scan-repo` — CI/CD Automated Webhook
Acts as a compliance gate in GitHub Actions. Evaluates pull request diffs and returns HTTP 200 for compliant proposals or HTTP 403 to block PR merging.
* **Headers**: `Authorization: Bearer <token>`
* **Request Body**:
  ```json
  {
    "repo_name": "fintech-corp/payments-service",
    "commit_hash": "9f8a3c2b1d0e4f5a6b7c8d9e0f1a2b3c4d5e6f7a",
    "architecture_changes": "Added automated facial biometrics for user credit profiling."
  }
  ```

---

## 🛡️ Security & Cryptographic Invariants

* **Tenant Cryptographic Isolation**: Canonical SHA-256 hashing includes `org_id` in serialized JSON payloads, ensuring hash blocks between different organizations never collide.
* **Zero Cloud Data Leakage**: Vector embeddings run locally via `sentence-transformers/all-MiniLM-L6-v2` on CPU.
* **Deterministic Hasher**: Canonical key sorting and strict whitespace separators guarantee identical hashes for identical inputs across platforms.
* **Append-Only Immutability**: All compliance audits and overrides are `INSERT`-only rows with PostgreSQL table-level locking to prevent race conditions or ledger forks.

---

## 📜 License & Copyright

**Copyright © 2026. All Rights Reserved.**

This repository, source code, architecture, and associated documentation are **Proprietary and Confidential**.

* **Permitted Use**: You are granted permission to view and examine this source code for personal review, evaluation, and educational demonstration purposes only.
* **Prohibited Use**: No part of this codebase may be copied, modified, redistributed, commercialized, sublicensed, or used in production systems without explicit, prior written permission from the copyright owner.
