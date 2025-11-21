# Alex – Installation & Deployment Guide

This document explains how to deploy **Alex (Agentic Learning Equities eXplainer)** to AWS and run it locally.
It is written so the project can stand alone outside the course materials.

Alex is a production‑style, serverless, multi‑agent financial planning platform. The full system includes:

- SageMaker serverless embeddings
- S3 Vectors for cost‑effective vector storage
- An App Runner research agent
- DynamoDB tables for portfolios, instruments, accounts, positions, and jobs
- Five Lambda‑based agents orchestrated via SQS
- A FastAPI backend on Lambda + API Gateway
- A Next.js + Clerk frontend on S3 + CloudFront
- Optional enterprise monitoring and observability

---

## 1. Prerequisites

- **AWS account** with an IAM user configured in your shell (`aws configure`)
- **Default region** (commonly `us-east-1`)
- **AWS CLI v2**
- **Terraform 1.5+**
- **Docker** (for Lambda packaging and App Runner images)
- **uv** (Python package/runtime manager)
- **Node.js 20+ and npm**
- **Clerk account** (for authentication)
- **AWS Bedrock model access** for **Amazon Nova Pro** (recommended) in at least one region
- (Optional) **Polygon.io API key** for live market data

Throughout this guide, paths are relative to the project root, which we’ll call `alex/`.

---

## 2. High‑Level Deployment Flow

You will deploy Alex in layers, each with its own Terraform stack:

1. **Clone repo & base environment**
2. **Embeddings** – SageMaker serverless endpoint (Terraform `terraform/2_sagemaker`)
3. **Ingestion & S3 Vectors** – Lambda + API Gateway + S3 Vectors (Terraform `terraform/3_ingestion`)
4. **Researcher** – App Runner service (Terraform `terraform/4_researcher`)
5. **Database** – DynamoDB tables (Terraform `terraform/5_database`)
6. **Agent Orchestra** – 5 Lambda agents + SQS (Terraform `terraform/6_agents`)
7. **Frontend & API** – API Lambda + CloudFront + S3 static site (Terraform `terraform/7_frontend`)
8. **Enterprise / Monitoring (optional)** – dashboards, WAF, observability (Terraform `terraform/8_enterprise`)

Local development (`scripts/run_local.py`) then uses the same AWS resources.

---

## 3. Step 1 – Clone & Base Environment

```bash
git clone <your-fork-or-clone-of-this-repo>
cd alex-agent

# Create base env file
cp .env.example .env
```

Edit `.env` and set at least:

```bash
AWS_ACCOUNT_ID=123456789012
DEFAULT_AWS_REGION=us-east-1
```

You will gradually fill in the remaining variables using Terraform outputs from later steps (S3 Vectors bucket, SageMaker endpoint name, database ARNs, SQS URL, etc.).

---

## 4. Step 2 – Embedding Endpoint (terraform/2_sagemaker)

This provisions a **SageMaker serverless endpoint** that hosts `sentence-transformers/all-MiniLM-L6-v2` for embeddings.

```bash
cd terraform/2_sagemaker
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`:

```hcl
aws_region = "us-east-1"  # or your preferred region
```

Deploy:

```bash
terraform init
terraform apply
```

After it completes, note the **endpoint name** (usually `alex-embedding-endpoint`) and update `.env` in the project root:

```bash
# Embeddings
SAGEMAKER_ENDPOINT=alex-embedding-endpoint
```

You can test the endpoint from `backend/` using the provided JSON payload if desired.

---

## 5. Step 3 – Ingestion & S3 Vectors (backend/ingest + terraform/3_ingestion)

This layer provides a **document ingestion pipeline**:

- S3 Vectors bucket and index
- Lambda function to call SageMaker and write to S3 Vectors
- API Gateway with API key, fronting the Lambda

### 5.1 Create S3 Vectors bucket & index

In the AWS console:

1. Open **Amazon S3** and choose **Vector buckets** (not standard buckets).
2. Create a vector bucket, e.g. `alex-vectors-<your-account-id>`.
3. Add an index, e.g. `financial-research`, with:
   - Dimension: `384`
   - Distance metric: `Cosine`

### 5.2 Package the ingest Lambda

```bash
cd backend/ingest
uv run package.py
```

This creates `lambda_function.zip` in `backend/ingest/`.

### 5.3 Deploy ingestion infrastructure

```bash
cd ../../terraform/3_ingestion
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` (values must match what you’ve already created):

```hcl
aws_region             = "us-east-1"
sagemaker_endpoint_name = "alex-embedding-endpoint"  # from Step 2
```

Deploy:

```bash
terraform init
terraform apply
```

After apply, capture the outputs and update `.env`:

```bash
VECTOR_BUCKET=alex-vectors-<your-account-id>
ALEX_API_ENDPOINT=https://xxxxx.execute-api.us-east-1.amazonaws.com/prod/ingest
ALEX_API_KEY=<api-key-value-from-aws>
```

You can test ingestion/search using the helper scripts in `backend/ingest/` (e.g. `uv run test_ingest_s3vectors.py`, `uv run test_search_s3vectors.py`).

---

## 6. Step 4 – Researcher Service (backend/researcher + terraform/4_researcher)

The **Researcher** is an App Runner service that:

- Calls AWS Bedrock (e.g. **Amazon Nova Pro**) via the OpenAI Agents SDK
- Browses the web via MCP for market data
- Writes research into the ingestion API you just created

### 6.1 Configure model & regions

Open `backend/researcher/server.py` and set the region/model you actually have access to, for example:

```python
REGION = "us-east-1"  # or us-west-2, etc.
os.environ["AWS_REGION_NAME"] = REGION
os.environ["AWS_REGION"] = REGION
os.environ["AWS_DEFAULT_REGION"] = REGION

MODEL = "bedrock/us.amazon.nova-pro-v1:0"  # recommended
```

Ensure you have requested access to that Bedrock model in the AWS console.

### 6.2 Environment variables

Add to `.env` (using values from previous steps):

```bash
OPENAI_API_KEY=sk-...              # used for tracing/observability
ALEX_API_ENDPOINT=...              # from Step 3
ALEX_API_KEY=...                   # from Step 3
```

### 6.3 Terraform configuration

```bash
cd terraform/4_researcher
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` with your values (OpenAI key, ingest API endpoint, API key, AWS region). First deploy the ECR repo and IAM roles:

```bash
terraform init
terraform apply \
  -target=aws_ecr_repository.researcher \
  -target=aws_iam_role.app_runner_role
```

### 6.4 Build and push the Docker image

```bash
cd ../../backend/researcher
uv run deploy.py
```

This builds an App Runner compatible image (linux/amd64) and pushes it to ECR.

### 6.5 Create the App Runner service

```bash
cd ../../terraform/4_researcher
terraform apply
```

The outputs include the **Researcher service URL**. You can test it via the included script:

```bash
cd ../../backend/researcher
uv run test_research.py
```

---

## 7. Step 5 – Database (terraform/5_database + backend/database)

This provisions **DynamoDB tables** for the logical database used by Alex.

### 7.1 Deploy DynamoDB tables

```bash
cd terraform/5_database
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` (typical dev settings):

```hcl
aws_region      = "us-east-1"   # Region for your DynamoDB tables
db_table_prefix = "alex_"       # Optional: logical prefix for table names
```

Deploy:

```bash
terraform init
terraform apply
```

After completion, Terraform will output a `setup_instructions` block that includes the table names and the environment variables you should set. In your `.env` file, add at minimum:

```bash
DB_TABLE_PREFIX=alex_            # or the prefix you used in terraform
DEFAULT_AWS_REGION=us-east-1
```

### 7.2 Initialize and seed data

From the backend database package:

```bash
cd ../../backend/database

# Create any required default data / indexes (idempotent)
uv run run_migrations.py

# Seed reference instruments
uv run seed_data.py

# Optionally reset and add test data
uv run reset_db.py --with-test-data

# Sanity check
uv run verify_database.py
```

After this step you have:

- DynamoDB tables for users, instruments, accounts, positions, jobs (with a shared prefix)
- Seed data (22 ETFs)
- Optional test user and sample portfolio

---

## 8. Step 6 – Agent Orchestra (backend/* agents + terraform/6_agents)

This layer deploys five specialized Lambda‑based agents plus an SQS queue used by the planner:

- **planner** – orchestrator
- **tagger** – instrument classification
- **reporter** – portfolio analysis
- **charter** – chart generation
- **retirement** – retirement projections

### 8.1 Configure agent‑related env

In `.env`, set at minimum:

```bash
BEDROCK_MODEL_ID=us.amazon.nova-pro-v1:0
BEDROCK_REGION=us-west-2      # or region where Nova Pro is enabled
DEFAULT_AWS_REGION=us-east-1  # Lambda/infra region
POLYGON_API_KEY=your-polygon-api-key
POLYGON_PLAN=free             # or the plan you use
VECTOR_BUCKET=alex-vectors-<your-account-id>
SAGEMAKER_ENDPOINT=alex-embedding-endpoint
```

### 8.2 Local agent smoke tests (optional but recommended)

From each agent directory (`backend/tagger`, `backend/reporter`, `backend/charter`, `backend/retirement`, `backend/planner`):

```bash
uv run test_simple.py
```

### 8.3 Package all Lambdas

From `backend/`:

```bash
cd ../backend
uv run package_docker.py
```

This builds `*_lambda.zip` artifacts for each agent using Docker.

### 8.4 Deploy Lambda + SQS infra

```bash
cd ../terraform/6_agents
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` with:

- `aws_region` – where your Lambdas live (e.g. `us-east-1`)
- `vector_bucket` – your S3 Vectors bucket
- `bedrock_model_id` / `bedrock_region`
- `sagemaker_endpoint`
- `polygon_api_key` / `polygon_plan`

Then deploy:

```bash
terraform init
terraform apply
```

Note the **SQS queue URL** in the outputs, and add it to `.env`:

```bash
SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/123456789012/alex-analysis-jobs
```

### 8.5 Force Lambda code refresh (if needed)

From `backend/`:

```bash
cd ../backend
uv run deploy_all_lambdas.py --package
```

You can now run the `test_full.py` scripts in each agent or in `backend/` to exercise the deployed Lambdas end‑to‑end.

---

## 9. Step 7 – Frontend & API (backend/api + terraform/7_frontend + scripts/deploy.py)

This step deploys:

- A **FastAPI** backend as a Lambda function behind **API Gateway**
- A **Next.js** frontend built to static files and hosted on **S3 + CloudFront**

### 9.1 Configure Clerk & API env

In the project root `.env`, add:

```bash
CLERK_JWKS_URL=https://<your-clerk-instance>.clerk.accounts.dev/.well-known/jwks.json
```

In `frontend/.env.local` (create if missing), configure:

```bash
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
NEXT_PUBLIC_CLERK_AFTER_SIGN_IN_URL=/dashboard
NEXT_PUBLIC_CLERK_AFTER_SIGN_UP_URL=/dashboard

# Local dev API URL; the production URL is injected at build time by scripts/deploy.py
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 9.2 Package the API Lambda

```bash
cd backend/api
uv run package_docker.py
```

This creates `api_lambda.zip`.

### 9.3 Deploy infra & frontend in one go

From `scripts/`:

```bash
cd ../../scripts
uv run deploy.py
```

This script will:

1. Package the API Lambda
2. Run Terraform in `terraform/7_frontend` to provision:
   - API Gateway + Lambda
   - S3 bucket for the frontend
   - CloudFront distribution
3. Build the Next.js app with the **production API URL**
4. Upload static files to S3 and invalidate CloudFront

At the end it prints the **CloudFront URL**, for example:

```text
https://dxxxxxxxxxxxx.cloudfront.net
```

The reference deployment of this repo is served at:

- **https://www.alexagent.pp.ua/**

If you own a custom domain, you can point it to your CloudFront distribution in Route 53 or your DNS provider.

---

## 10. Step 8 – Enterprise Monitoring & Observability (terraform/8_enterprise)

The final Terraform stack adds enterprise‑style monitoring and guardrails, such as:

- CloudWatch dashboards and alarms
- Enhanced metrics for Bedrock and SageMaker
- Optional WAF / GuardDuty / VPC endpoints (depending on configuration)

```bash
cd ../terraform/8_enterprise
cp terraform.tfvars.example terraform.tfvars

terraform init
terraform apply
```

Follow the outputs to open the dashboards and verify metrics in the AWS console.

---

## 11. Local Development

Once your AWS infrastructure is deployed and `.env` / `frontend/.env.local` are populated, you can run Alex locally:

```bash
cd scripts
uv run run_local.py
```

This will:

- Start the FastAPI backend on `http://localhost:8000`
- Start the Next.js frontend on `http://localhost:3000`

API calls from the local backend will still talk to your deployed AWS resources (Aurora, Lambda agents, S3 Vectors, etc.).

---

## 12. Teardown & Cost Management

Most of Alex is serverless and low‑cost. DynamoDB tables use on‑demand (PAY_PER_REQUEST) billing with near‑zero idle cost, but **Bedrock**, **App Runner**, and S3 Vectors usage can still add up. When you’re not actively using the system, consider tearing down stacks.

Destroy in (roughly) reverse order of deployment:

```bash
# From each terraform directory
cd terraform/8_enterprise && terraform destroy
cd ../7_frontend && terraform destroy
cd ../6_agents && terraform destroy
cd ../5_database && terraform destroy   # biggest cost savings
cd ../4_researcher && terraform destroy
cd ../3_ingestion && terraform destroy
cd ../2_sagemaker && terraform destroy
```

You can always recreate everything later by re‑running the steps above.

---

## 13. Troubleshooting Pointers

Common issues to check before debugging code:

- **Docker not running** – packaging scripts fail or Lambda zips are missing
- **Terraform variables not set** – every Terraform directory needs a populated `terraform.tfvars`
- **AWS region mismatches** – Bedrock model region vs Lambda region vs your `DEFAULT_AWS_REGION`
- **Bedrock model access** – ensure Nova Pro (or your chosen model) is approved in the Bedrock console
- **Database prefix / tables** – confirm `terraform/5_database` applied successfully and `DB_TABLE_PREFIX` in `.env` matches the prefix used in Terraform
- **Missing environment variables** – compare your `.env` against `.env.example` and the Terraform outputs

With the infrastructure deployed and env files correctly configured, you should be able to:

- Create an account and sign in via Clerk
- Populate a sample portfolio
- Trigger an end‑to‑end multi‑agent analysis
- View reports, charts, and retirement projections in the frontend.
