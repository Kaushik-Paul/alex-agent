"""
Financial Planner Orchestrator Agent - coordinates portfolio analysis across specialized agents.
"""

import os
import json
import boto3
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
from botocore.exceptions import ClientError
from src import Database

from agents import function_tool, RunContextWrapper
from agents.extensions.models.litellm_model import LitellmModel

logger = logging.getLogger()

# Initialize Lambda client
lambda_client = boto3.client("lambda")

# Lambda function names from environment
TAGGER_FUNCTION = os.getenv("TAGGER_FUNCTION", "alex-tagger")
REPORTER_FUNCTION = os.getenv("REPORTER_FUNCTION", "alex-reporter")
CHARTER_FUNCTION = os.getenv("CHARTER_FUNCTION", "alex-charter")
RETIREMENT_FUNCTION = os.getenv("RETIREMENT_FUNCTION", "alex-retirement")
MOCK_LAMBDAS = os.getenv("MOCK_LAMBDAS", "false").lower() == "true"


@dataclass
class PlannerContext:
    """Context for planner agent tools."""
    job_id: str


async def invoke_lambda_agent(
    agent_name: str, function_name: str, payload: Dict[str, Any]
) -> Dict[str, Any]:
    """Invoke a Lambda function for an agent."""

    # For local testing with mocked agents
    if MOCK_LAMBDAS:
        logger.info(f"[MOCK] Would invoke {agent_name} with payload: {json.dumps(payload)[:200]}")
        return {"success": True, "message": f"[Mock] {agent_name} completed", "mock": True}

    try:
        logger.info(f"Invoking {agent_name} Lambda: {function_name}")

        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload),
        )

        result = json.loads(response["Payload"].read())

        # Unwrap Lambda response if it has the standard format
        if isinstance(result, dict) and "statusCode" in result and "body" in result:
            if isinstance(result["body"], str):
                try:
                    result = json.loads(result["body"])
                except json.JSONDecodeError:
                    result = {"message": result["body"]}
            else:
                result = result["body"]

        logger.info(f"{agent_name} completed successfully")
        return result

    except Exception as e:
        logger.error(f"Error invoking {agent_name}: {e}")
        return {"error": str(e)}


def handle_missing_instruments(job_id: str, db) -> None:
    """
    Check for and tag any instruments missing allocation data.
    This is done automatically before the agent runs.
    """
    logger.info("Planner: Checking for instruments missing allocation data...")

    # Get job and portfolio data
    job = db.jobs.find_by_id(job_id)
    if not job:
        logger.error(f"Job {job_id} not found")
        return

    # Enforce tagger run cap per job
    tagger_runs = int(job.get("tagger_runs", 0) or 0)
    if tagger_runs >= 5:
        logger.info(f"Planner: Tagger run cap reached for job {job_id} (runs={tagger_runs}). Skipping tagging.")
        return

    user_id = job["clerk_user_id"]
    accounts = db.accounts.find_by_user(user_id)

    missing = []
    for account in accounts:
        positions = db.positions.find_by_account(account["id"])
        for position in positions:
            instrument = db.instruments.find_by_symbol(position["symbol"])
            if instrument:
                has_allocations = bool(
                    instrument.get("allocation_regions")
                    and instrument.get("allocation_sectors")
                    and instrument.get("allocation_asset_class")
                )
                price_missing = not instrument.get("current_price") or float(instrument.get("current_price") or 0) <= 0
                # Consider price stale if last update was more than 7 days ago (or unknown)
                price_stale = False
                try:
                    last_price_updated_at = instrument.get("last_price_updated_at")
                    if last_price_updated_at:
                        last_dt = datetime.fromisoformat(str(last_price_updated_at))
                        if datetime.utcnow() - last_dt > timedelta(days=7):
                            price_stale = True
                    else:
                        # If we have a price but no timestamp, treat as stale to force a refresh once
                        if instrument.get("current_price"):
                            price_stale = True
                except Exception:
                    price_stale = True
                name_val = instrument.get("name", "")
                is_placeholder_name = isinstance(name_val, str) and name_val.endswith(" - User Added")
                # Only re-tag if allocations are missing or price is missing.
                # Do NOT re-tag solely due to placeholder name if data is otherwise complete.
                # Also re-tag if price is stale (> 7 days) to refresh the latest price from tagger.
                if (not has_allocations) or price_missing or price_stale:
                    missing.append(
                        {"symbol": position["symbol"], "name": instrument.get("name", "")}
                    )
            else:
                missing.append({"symbol": position["symbol"], "name": ""})

    # Dedupe by symbol to avoid repeated classifications
    if missing:
        dedup = {}
        for m in missing:
            sym = m.get("symbol")
            if sym and sym not in dedup:
                dedup[sym] = m
        missing = list(dedup.values())
        # Record Tagger invocation; allow multiple runs per job up to cap
        try:
            table = db.client.table('jobs')
            now_iso = datetime.utcnow().isoformat()
            table.update_item(
                Key={'id': job_id},
                UpdateExpression='SET tagger_started_at = if_not_exists(tagger_started_at, :t), tagger_runs = if_not_exists(tagger_runs, :zero) + :one',
                ExpressionAttributeValues={':t': now_iso, ':zero': 0, ':one': 1}
            )
        except Exception as e:
            logger.warning(f"Planner: Could not update tagger run metadata for job {job_id}: {e}")

        # Limit number of instruments per tagger call to keep runtime tight
        try:
            max_per_call = int(os.getenv("TAGGER_MAX_PER_CALL", "12"))
        except Exception:
            max_per_call = 12
        logger.info(f"Planner: Using TAGGER_MAX_PER_CALL={max_per_call}")
        if len(missing) > max_per_call:
            logger.info(f"Planner: Limiting tagger batch from {len(missing)} to {max_per_call} instruments")
            missing = missing[:max_per_call]

        logger.info(
            f"Planner: Found {len(missing)} instruments needing classification: {[m['symbol'] for m in missing]}"
        )

        try:
            response = lambda_client.invoke(
                FunctionName=TAGGER_FUNCTION,
                InvocationType="RequestResponse",
                Payload=json.dumps({"job_id": job_id, "instruments": missing}),
            )

            result = json.loads(response["Payload"].read())

            if isinstance(result, dict) and "statusCode" in result:
                if result["statusCode"] == 200:
                    logger.info(
                        f"Planner: InstrumentTagger completed - Tagged {len(missing)} instruments"
                    )
                    try:
                        db.client.update_item('jobs', {"id": job_id}, {"tagger_completed": True, "tagger_finished_at": datetime.utcnow().isoformat()})
                    except Exception:
                        pass
                else:
                    logger.error(
                        f"Planner: InstrumentTagger failed with status {result['statusCode']}"
                    )

        except Exception as e:
            logger.error(f"Planner: Error tagging instruments: {e}")
    else:
        logger.info("Planner: All instruments have allocation data")
        try:
            db.client.update_item('jobs', {"id": job_id}, {"tagger_completed": True})
        except Exception:
            pass

    # Tagging step complete (either no missing or successfully tagged)


def load_portfolio_summary(job_id: str, db) -> Dict[str, Any]:
    """Load basic portfolio summary statistics only."""
    try:
        job = db.jobs.find_by_id(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        user_id = job["clerk_user_id"]
        user = db.users.find_by_clerk_id(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")

        accounts = db.accounts.find_by_user(user_id)
        
        # Calculate simple summary statistics
        total_value = 0.0
        total_positions = 0
        total_cash = 0.0
        
        for account in accounts:
            total_cash += float(account.get("cash_balance", 0))
            positions = db.positions.find_by_account(account["id"])
            total_positions += len(positions)
            
            # Add position values
            for position in positions:
                instrument = db.instruments.find_by_symbol(position["symbol"])
                if instrument and instrument.get("current_price"):
                    price = float(instrument["current_price"])
                    quantity = float(position["quantity"])
                    total_value += price * quantity
        
        total_value += total_cash
        
        # Return only summary statistics
        return {
            "total_value": total_value,
            "num_accounts": len(accounts),
            "num_positions": total_positions,
            "years_until_retirement": user.get("years_until_retirement", 30),
            "target_retirement_income": float(user.get("target_retirement_income", 80000))
        }

    except Exception as e:
        logger.error(f"Error loading portfolio summary: {e}")
        raise


async def invoke_reporter_internal(job_id: str) -> str:
    """
    Invoke the Report Writer Lambda to generate portfolio analysis narrative.

    Args:
        job_id: The job ID for the analysis

    Returns:
        Confirmation message
    """
    # Precondition: if tagger is in progress, defer reporter
    try:
        _db = Database()
        job = _db.jobs.find_by_id(job_id)
    except Exception:
        job = None
    if job and job.get("tagger_started_at") and not job.get("tagger_completed"):
        return "Reporter deferred: Tagger in progress."

    # Idempotency: skip if already has report payload
    if job and job.get("report_payload"):
        return "Reporter agent already completed previously. Skipping."

    # Proceed without phase gating

    # Single-invocation lock using DynamoDB conditional update
    try:
        table = Database().client.table('jobs')
        now_iso = datetime.utcnow().isoformat()
        table.update_item(
            Key={'id': job_id},
            UpdateExpression='SET reporter_started_at = if_not_exists(reporter_started_at, :t), reporter_invocations = if_not_exists(reporter_invocations, :zero) + :one',
            ConditionExpression='attribute_not_exists(reporter_started_at)',
            ExpressionAttributeValues={':t': now_iso, ':zero': 0, ':one': 1}
        )
    except ClientError as e:
        if e.response.get('Error', {}).get('Code') == 'ConditionalCheckFailedException':
            return "Reporter agent already invoked previously. Skipping."
        else:
            raise

    result = await invoke_lambda_agent("Reporter", REPORTER_FUNCTION, {"job_id": job_id})

    # Continue to next step

    if "error" in result:
        return f"Reporter agent failed: {result['error']}"

    return "Reporter agent completed successfully. Portfolio analysis narrative has been generated and saved."


async def invoke_charter_internal(job_id: str) -> str:
    """
    Invoke the Chart Maker Lambda to create portfolio visualizations.

    Args:
        job_id: The job ID for the analysis

    Returns:
        Confirmation message
    """
    # Record metadata for Charter invocation; allow re-invocation if charts not present
    try:
        table = Database().client.table('jobs')
        now_iso = datetime.utcnow().isoformat()
        table.update_item(
            Key={'id': job_id},
            UpdateExpression='SET charter_started_at = if_not_exists(charter_started_at, :t), charter_invocations = if_not_exists(charter_invocations, :zero) + :one',
            ExpressionAttributeValues={':t': now_iso, ':zero': 0, ':one': 1}
        )
    except Exception as e:
        logger.warning(f"Planner: Could not update charter metadata for job {job_id}: {e}")

    # Proceed without phase gating

    # Always attempt invocation; Charter Lambda itself is idempotent and will skip if charts exist

    result = await invoke_lambda_agent(
        "Charter", CHARTER_FUNCTION, {"job_id": job_id}
    )

    if "error" in result:
        return f"Charter agent failed: {result['error']}"

    # Continue to next step

    return "Charter agent completed successfully. Portfolio visualizations have been created and saved."


async def invoke_retirement_internal(job_id: str) -> str:
    """
    Invoke the Retirement Specialist Lambda for retirement projections.

    Args:
        job_id: The job ID for the analysis

    Returns:
        Confirmation message
    """
    # Single-invocation lock using DynamoDB conditional update
    try:
        table = Database().client.table('jobs')
        now_iso = datetime.utcnow().isoformat()
        table.update_item(
            Key={'id': job_id},
            UpdateExpression='SET retirement_started_at = if_not_exists(retirement_started_at, :t), retirement_invocations = if_not_exists(retirement_invocations, :zero) + :one',
            ConditionExpression='attribute_not_exists(retirement_started_at)',
            ExpressionAttributeValues={':t': now_iso, ':zero': 0, ':one': 1}
        )
    except ClientError as e:
        if e.response.get('Error', {}).get('Code') == 'ConditionalCheckFailedException':
            return "Retirement agent already invoked previously. Skipping."
        else:
            raise

    # Proceed without phase gating

    # Idempotency: skip if retirement analysis already exists
    try:
        _db = Database()
        job = _db.jobs.find_by_id(job_id)
    except Exception:
        job = None
    if job and job.get("retirement_payload"):
        return "Retirement agent already completed previously. Skipping."

    result = await invoke_lambda_agent("Retirement", RETIREMENT_FUNCTION, {"job_id": job_id})

    if "error" in result:
        return f"Retirement agent failed: {result['error']}"

    # Final step complete

    return "Retirement agent completed successfully. Retirement projections have been calculated and saved."



@function_tool
async def invoke_reporter(wrapper: RunContextWrapper[PlannerContext]) -> str:
    """Invoke the Report Writer agent to generate portfolio analysis narrative."""
    return await invoke_reporter_internal(wrapper.context.job_id)

@function_tool
async def invoke_charter(wrapper: RunContextWrapper[PlannerContext]) -> str:
    """Invoke the Chart Maker agent to create portfolio visualizations."""
    return await invoke_charter_internal(wrapper.context.job_id)

@function_tool
async def invoke_retirement(wrapper: RunContextWrapper[PlannerContext]) -> str:
    """Invoke the Retirement Specialist agent for retirement projections."""
    return await invoke_retirement_internal(wrapper.context.job_id)


def create_agent(job_id: str, portfolio_summary: Dict[str, Any], db):
    """Create the orchestrator agent with tools."""
    
    # Create context for tools
    context = PlannerContext(job_id=job_id)

    # Get model configuration
    model_id = os.getenv("OPENROUTER_MODEL_ID", "nvidia/nemotron-nano-12b-v2-vl:free")
    # Set region for LiteLLM Bedrock calls
    bedrock_region = os.getenv("BEDROCK_REGION", "us-west-2")
    os.environ["AWS_REGION_NAME"] = bedrock_region

    model = LitellmModel(model=f"openrouter/{model_id}")

    tools = [
        invoke_reporter,
        invoke_charter,
        invoke_retirement,
    ]

    # Create minimal task context
    task = f"""Job {job_id} has {portfolio_summary['num_positions']} positions.
Retirement: {portfolio_summary['years_until_retirement']} years.

Call the appropriate agents."""

    return model, tools, task, context
