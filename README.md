## Alex - the Agentic Learning Equities Explainer

[![Live App](https://img.shields.io/badge/Live_App-alexagent.pp.ua-6c63ff?logo=amazonaws&logoColor=white&labelColor=5a52d3)](https://www.alexagent.pp.ua/)

Alex is a **multi-agent, serverless financial planning platform**. It analyzes equity portfolios, projects retirement outcomes, and explains its reasoning in clear, investor-friendly language.

## Features

- **Multi-agent AI advisor**  
  Five specialized agents collaborate:
  - Planner (orchestrator)
  - Tagger (instrument classification)
  - Reporter (portfolio analysis)
  - Charter (charting & visualizations)
  - Retirement (retirement projections)

- **Portfolio management UI**  
  - Clerk-based sign-in/sign-up  
  - Create investment accounts (401k, IRA, taxable, etc.)  
  - Add/edit/delete positions and cash balances  
  - One-click population of realistic test data

- **Research knowledge base**  
  - App Runner research agent that fetches market intel via the web  
  - SageMaker serverless embeddings (MiniLM)  
  - S3 Vectors for low-cost semantic search (≈90% cheaper than typical vector DBs)

- **Retirement planning**  
  - Monte Carlo-style projections  
  - Success probabilities and projected income  
  - Recommendations to improve retirement readiness

- **Enterprise-grade architecture**  
  - Serverless backend on AWS (Lambda, DynamoDB, API Gateway, SQS, App Runner)  
  - Next.js frontend on S3 + CloudFront with Clerk authentication  
  - Optional monitoring, guardrails, and observability (CloudWatch, WAF, LangFuse)

## Architecture Overview

At a high level, Alex is composed of four layers:

- **Frontend**  
  - Next.js React app (Pages Router)  
  - Clerk authentication  
  - Deployed as static assets to S3 and served via CloudFront

- **Backend API**  
  - FastAPI application exposed through API Gateway + Lambda (via Mangum)  
  - Handles authentication (Clerk JWT verification), portfolio CRUD, and analysis job orchestration

- **Data & Research**  
  - DynamoDB tables for user portfolios, instruments, accounts, positions, jobs  
  - SageMaker serverless endpoint for embeddings (MiniLM)  
  - S3 Vectors for vector search  
  - Ingestion Lambda + API Gateway endpoint for storing research and documents  
  - App Runner "Researcher" service that periodically generates and stores market insights

- **Agent Orchestra**  
  - Planner receives portfolio analysis requests via SQS  
  - Delegates work to Tagger, Reporter, Charter, and Retirement agents  
  - Each agent is a Lambda function implemented with the OpenAI Agents SDK and writes its results back to the database  
  - Jobs track the full lifecycle and combine results into a single analysis view

## Tech Stack

| Category           | Technologies |
|--------------------|-------------|
| **Frontend**       | Next.js 15 (Pages Router), React 19, TypeScript, Tailwind-style utilities, Recharts |
| **Backend API**    | FastAPI, Mangum (Lambda adapter), Pydantic, `uv` for Python env management |
| **Agents**         | `openai-agents` (OpenAI Agents SDK), Pydantic AI, AWS Bedrock (Nova Pro / OSS models) |
| **Data & Search**  | DynamoDB (on-demand tables), S3 Vectors, SageMaker serverless embeddings |
| **Infra**          | AWS Lambda, App Runner, API Gateway, SQS, CloudFront, S3, Terraform |
| **Auth & Obs.**    | Clerk, AWS CloudWatch, optional WAF/GuardDuty, LangFuse traces |

All Python services use **uv**; there is no `pip install` or `python script.py` anywhere in the workflow.

## Repository Layout

```text
alex/
├── backend/              # Agent code, Lambdas, researcher service, shared DB lib, FastAPI API
│   ├── api/              # FastAPI backend (Lambda handler + local dev entrypoint)
│   ├── database/         # DynamoDB client/wrapper, migrations, seed/verify scripts
│   ├── planner/          # Orchestrator agent
│   ├── tagger/           # Instrument classification agent
│   ├── reporter/         # Portfolio analysis agent
│   ├── charter/          # Charting/visualization agent
│   ├── retirement/       # Retirement projection agent
│   ├── ingest/           # Document ingestion Lambda (S3 Vectors + SageMaker)
│   └── researcher/       # App Runner research service
│
├── frontend/             # Next.js + Clerk frontend
│   ├── pages/            # Pages Router routes (landing, dashboard, accounts, analysis)
│   ├── components/       # UI components (charts, tables, layouts)
│   └── styles/           # Global styles
│
├── terraform/            # Independent Terraform stacks
│   ├── 2_sagemaker/      # SageMaker serverless endpoint
│   ├── 3_ingestion/      # S3 Vectors bucket, ingest Lambda, API Gateway
│   ├── 4_researcher/     # App Runner research service
│   ├── 5_database/       # DynamoDB tables (users, instruments, accounts, positions, jobs)
│   ├── 6_agents/         # Multi-agent Lambdas + SQS orchestration
│   ├── 7_frontend/       # API Lambda + CloudFront + S3 static hosting
│   └── 8_enterprise/     # Optional monitoring, guardrails, observability
│
└── scripts/              # Helper scripts
    ├── run_local.py      # Start FastAPI + Next.js locally (dev experience)
    ├── deploy.py         # Package API, deploy infra, build & upload frontend
    └── destroy.py        # Optional helper for tearing down stacks
```

## Quick Start (Local Development)

Local development assumes you have:

- An AWS account and IAM user configured (`aws sts get-caller-identity` works)
- Required infrastructure deployed (see **INSTALLATION.md**) or at least the core stacks (embeddings, ingestion, DB, agents, frontend API)
- `.env` and `frontend/.env.local` created and populated

### 1. Install prerequisites

- Install **Docker**, **Terraform**, **uv**, **Node.js 20+**, and **npm**.

### 2. Configure environment files

1. From the project root:

   ```bash
   cp .env.example .env
   ```

   Fill in values as you deploy infrastructure (AWS account/region, SageMaker endpoint, S3 Vectors bucket, database configuration such as DB_TABLE_PREFIX, SQS queue URL, Bedrock model, etc.).

2. In `frontend/.env.local`, configure Clerk and the local API URL, for example:

   ```bash
   NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
   CLERK_SECRET_KEY=sk_test_...
   NEXT_PUBLIC_CLERK_AFTER_SIGN_IN_URL=/dashboard
   NEXT_PUBLIC_CLERK_AFTER_SIGN_UP_URL=/dashboard
   NEXT_PUBLIC_API_URL=http://localhost:8000
   ```

### 3. Run backend + frontend together

Use the provided helper script (recommended):

```bash
cd scripts
uv run run_local.py
```

This will:

- Start the FastAPI backend at `http://localhost:8000`  
- Start the Next.js frontend at `http://localhost:3000`  
- Check for basic prerequisites and env files

Sign in via Clerk, populate a sample portfolio from the UI, and trigger an analysis to see the full multi-agent pipeline in action.

## Deployment & Infrastructure

All production infrastructure is managed by **Terraform** using **independent directories** under `terraform/`.

The common pattern for each stack is:

```bash
cd terraform/<stack_name>        # e.g. 5_database, 6_agents, 7_frontend
cp terraform.tfvars.example terraform.tfvars

terraform init
terraform plan
terraform apply
```

The Terraform stacks are:

- **2_sagemaker** – SageMaker serverless endpoint for embeddings
- **3_ingestion** – S3 Vectors bucket, ingest Lambda, API Gateway
- **4_researcher** – App Runner research service and (optionally) scheduler
- **5_database** – DynamoDB tables (users, instruments, accounts, positions, jobs)
- **6_agents** – Five Lambda agents, SQS queue, IAM roles, S3 for packages
- **7_frontend** – API Lambda, API Gateway, S3 static site, CloudFront
- **8_enterprise** – Optional monitoring, dashboards, guardrails, observability

For a step‑by‑step deployment walkthrough (including which Terraform outputs map to which environment variables), see **[INSTALLATION.md](./INSTALLATION.md)**.

## Environment Variables (Overview)

Key groups of variables (see `.env.example` for a complete list):

- **Core AWS config**  
  - `AWS_ACCOUNT_ID`  
  - `DEFAULT_AWS_REGION`

- **Embeddings & Vectors**  
  - `SAGEMAKER_ENDPOINT` – SageMaker serverless endpoint name  
  - `VECTOR_BUCKET` – S3 Vectors bucket name  
  - `ALEX_API_ENDPOINT`, `ALEX_API_KEY` – ingest API Gateway endpoint and key

- **Database**  
  - `DB_TABLE_PREFIX` – logical prefix for DynamoDB table names (e.g. `alex_`)

- **Agents & Bedrock**  
  - `BEDROCK_MODEL_ID` – e.g. `us.amazon.nova-pro-v1:0`  
  - `BEDROCK_REGION` – Bedrock model region (often `us-west-2` for Nova)  
  - `SQS_QUEUE_URL` – analysis jobs queue  
  - `POLYGON_API_KEY`, `POLYGON_PLAN` – market data integration (optional)

- **Auth & Frontend**  
  - `CLERK_JWKS_URL` – Clerk JWKS URL for backend JWT validation  
  - `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`, `NEXT_PUBLIC_API_URL` in `frontend/.env.local`

Refer to **INSTALLATION.md** for how these values are derived from Terraform outputs.

## Course Context

Alex is used as a capstone project in the **AI in Production** course. The repo is structured so that:

- Each major AWS component has its own Terraform stack under `terraform/`  
- Python services share a common database library and testing approach (`test_simple.py` for local mocks, `test_full.py` for deployed resources)  
- Students and practitioners can study a realistic, multi-agent, serverless SaaS end‑to‑end.

You can use this repo either as a reference architecture or as a starting point for your own AI‑powered financial tools.

## License

This project is licensed under the MIT License. See the [LICENSE](./LICENSE) file for details.
