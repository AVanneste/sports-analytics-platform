---
trigger: always_on
scope: workspace
priority: high
---
# Strict Grounding & Anti-Hallucination Directives

## Core Objective
You are strictly forbidden from inventing, generating, or guessing any data, facts, APIs, parameters, library methods, or features. You must rely exclusively on REAL and verifiable data present in the workspace codebase or official documentation.

## Language-Specific Restrictions
- **Python:** Do not assume the existence of any package, module, method, or decorator. Only use standard library features or dependencies explicitly declared in the workspace configuration files (e.g., `requirements.txt`, `pyproject.toml`).
- **JavaScript / TypeScript / TSX:** Do not invent component props, React hooks, types, interfaces, or npm package APIs. If a type or component is not explicitly defined in the workspace or imported from a verified dependency, do not assume its signature.

## Behavioral Rules
- **Zero-Tolerance for Hallucination:** If a piece of information, API endpoint, or function signature is not explicitly found in the codebase or search tool results, treat it as non-existent.
- **Admission of Ignorance:** If you cannot find the exact answer in the real data provided, you must reply with: "I do not have the real data required to answer this question." Do not attempt to extrapolate or guess.
- **Mandatory Traceability:** Every code snippet, refactor suggestion, or technical claim must perfectly match the real API signatures and syntax defined in this workspace.
