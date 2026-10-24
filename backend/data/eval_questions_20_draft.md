<!-- DRAFT FOR ZAIN'S REVIEW -->

# FinSight RegTech - Synthetic Regulatory Evaluation Benchmark (20 Questions Draft)

> [!IMPORTANT]
> **Status: DRAFT FOR REVIEW**
> This dataset comprises 20 synthetic regulatory compliance questions mapped to official EU statutory frameworks and their exact articles.
> **No premature accuracy or retrieval precision percentages are reported** until this benchmark is approved and systematically executed against the evaluation harness.

---

### Coverage Matrix (All 8 Ingested European Statutes)

| ID | EU Act | Article Target | Raw Source File | Regulatory Compliance Question | Expected Compliance Focus | Status |
| :---: | :---: | :---: | :---: | :--- | :--- | :---: |
| **Q01** | **PSD2** | Article 97 | `psd2_raw.txt` | What are the exact statutory requirements under PSD2 for applying Strong Customer Authentication (SCA) when a payer initiates an electronic payment transaction? | SCA mandate for remote electronic payments | `DRAFT` |
| **Q02** | **PSD2** | Article 66 | `psd2_raw.txt` | Under what statutory conditions may a payment initiation service provider (PISP) access a payer's payment account without establishing a contractual relationship with the ASPSP? | PISP access rights & open banking interfaces | `DRAFT` |
| **Q03** | **PSD2** | Article 98 | `psd2_raw.txt` | What mandates does PSD2 specify for EBA Regulatory Technical Standards (RTS) regarding exemptions to Strong Customer Authentication (SCA)? | Low-value & trusted beneficiary SCA exemptions | `DRAFT` |
| **Q04** | **GDPR** | Article 6 | `gdpr_raw.txt` | What constitutes a lawful basis for processing personal transaction data for legal compliance and anti-money laundering reporting under GDPR Article 6(1)(c)? | Lawfulness of processing for legal compliance | `DRAFT` |
| **Q05** | **GDPR** | Article 17 | `gdpr_raw.txt` | How does the GDPR Article 17(3)(b) exemption apply to the right to erasure ('right to be forgotten') when financial records must be retained on an immutable audit ledger? | Ledger retention vs right to erasure exemption | `DRAFT` |
| **Q06** | **GDPR** | Article 25 | `gdpr_raw.txt` | What technical and organizational measures (such as automated pseudonymization and PII masking) are required to satisfy Data Protection by Design and by Default? | Privacy by design via automated PII tokenization | `DRAFT` |
| **Q07** | **MiCA** | Article 16 | `mica_raw.txt` | What authorization requirements must an issuer of Asset-Referenced Tokens (ART) meet before offering them publicly to the European Union market? | Authorization & whitepaper requirements for ARTs | `DRAFT` |
| **Q08** | **MiCA** | Article 48 | `mica_raw.txt` | Under MiCA Article 48, which specific categories of entities are legally permitted to issue E-Money Tokens (EMTs) within the EU? | E-money tokens restricted to credit/EMIs | `DRAFT` |
| **Q09** | **MiCA** | Article 88 | `mica_raw.txt` | What measures and systems are crypto-asset service providers required to establish to prevent and detect insider dealing and market manipulation? | Market abuse prevention & surveillance systems | `DRAFT` |
| **Q10** | **DORA** | Article 5 | `dora_raw.txt` | What governance framework and operational controls must financial entities implement under DORA Article 5 for managing Information and Communication Technology (ICT) risk? | ICT risk management & management body oversight | `DRAFT` |
| **Q11** | **DORA** | Article 16 | `dora_raw.txt` | What simplified ICT risk management framework is available for small and non-interconnected entities under DORA Article 16? | Proportionality & simplified ICT risk controls | `DRAFT` |
| **Q12** | **DORA** | Article 28 | `dora_raw.txt` | What contractual and security principles must financial institutions enforce when managing third-party ICT service provider dependencies under DORA? | Critical ICT third-party dependency governance | `DRAFT` |
| **Q13** | **EU AI Act** | Article 6 & Annex III | `eu_ai_act_raw.txt` | Under the EU AI Act classification rules in Article 6 and Annex III, how are AI systems used for credit scoring and financial risk assessments classified? | High-risk classification of credit AI algorithms | `DRAFT` |
| **Q14** | **EU AI Act** | Article 14 | `eu_ai_act_raw.txt` | What human oversight measures must high-risk AI decision systems incorporate to ensure natural persons can intervene, override, or halt automated verdicts? | Human-in-the-loop controls & manual overrides | `DRAFT` |
| **Q15** | **EU AI Act** | Article 50 | `eu_ai_act_raw.txt` | What transparency obligations apply to AI systems that generate or manipulate regulatory texts and synthetic compliance decisions? | Transparency & synthetic output disclosures | `DRAFT` |
| **Q16** | **TFR** | Article 14 | `tfr_raw.txt` | Under EU Regulation 2023/1113 (Transfer of Funds / Travel Rule), what originator and beneficiary identity data must accompany a crypto-asset transfer? | Mandatory Travel Rule identity payload | `DRAFT` |
| **Q17** | **TFR** | Article 16 | `tfr_raw.txt` | What obligations are imposed on intermediary Crypto-Asset Service Providers (CASPs) regarding incomplete or missing originator information during transmission? | Intermediary CASP missing information checks | `DRAFT` |
| **Q18** | **AMLD5** | Article 30 | `amld5_raw.txt` | What statutory mandates did AMLD5 introduce regarding public and competent authority access to central registers of beneficial ownership? | Central beneficial ownership register access | `DRAFT` |
| **Q19** | **AMLD5** | Article 47 | `amld5_raw.txt` | What registration and licensing requirements are imposed on providers engaged in exchange services between virtual currencies and fiat currencies under AMLD5? | Mandatory registration of VASP/crypto exchanges | `DRAFT` |
| **Q20** | **AMLD6** | Article 7 | `amld6_raw.txt` | Under Directive (EU) 2018/1673 (AMLD6), under what circumstances are legal persons held criminally liable for money laundering offenses committed for their benefit? | Corporate criminal liability for money laundering | `DRAFT` |

---
