"""
Financial Planner Orchestrator Lambda Handler
"""

import os
import json
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any

from agents import Agent, Runner, trace
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from litellm.exceptions import RateLimitError

try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass

# Import database package
from src import Database

from templates import ORCHESTRATOR_INSTRUCTIONS
from agent import create_agent, handle_missing_instruments, load_portfolio_summary, invoke_reporter_internal, invoke_charter_internal, invoke_retirement_internal
from market import update_instrument_prices
from observability import observe

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize database
db = Database()

@retry(
    retry=retry_if_exception_type(RateLimitError),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    before_sleep=lambda retry_state: logger.info(f"Planner: Rate limit hit, retrying in {retry_state.next_action.sleep} seconds...")
)
async def run_orchestrator(job_id: str) -> None:
    """Run the orchestrator agent to coordinate portfolio analysis."""
    try:
        # Update job status to running
        db.jobs.update_status(job_id, 'running')
        
        # Handle missing instruments first (non-agent pre-processing)
        await asyncio.to_thread(handle_missing_instruments, job_id, db)

        # Update instrument prices after tagging
        logger.info("Planner: Updating instrument prices from market data")
        await asyncio.to_thread(update_instrument_prices, job_id, db)

        # Load portfolio summary (just statistics, not full data)
        portfolio_summary = await asyncio.to_thread(load_portfolio_summary, job_id, db)
        
        # Deterministic orchestrator by default to prevent LLM loops
        mode = os.getenv("ORCHESTRATOR_MODE", "deterministic").lower()
        if mode == "deterministic":
            # Run agents sequentially to avoid any residual race conditions
            _ = await invoke_reporter_internal(job_id)
            _ = await invoke_charter_internal(job_id)
            _ = await invoke_retirement_internal(job_id)
        else:
            model, tools, task, context = create_agent(job_id, portfolio_summary, db)
            with trace("Planner Orchestrator"):
                from agent import PlannerContext
                agent = Agent[PlannerContext](
                    name="Financial Planner",
                    instructions=ORCHESTRATOR_INSTRUCTIONS,
                    model=model,
                    tools=tools
                )
                await Runner.run(
                    agent,
                    input=task,
                    context=context,
                    max_turns=8
                )
        
        # Mark job as completed after all agents finish
        db.jobs.update_status(job_id, "completed")
        logger.info(f"Planner: Job {job_id} completed successfully")
            
    except Exception as e:
        logger.error(f"Planner: Error in orchestration: {e}", exc_info=True)
        db.jobs.update_status(job_id, 'failed', error_message=str(e))
        raise

def lambda_handler(event, context):
    """
    Lambda handler for SQS-triggered orchestration.

    Expected event from SQS:
    {
        "Records": [
            {
                "body": "job_id"
            }
        ]
    }
    """
    # Wrap entire handler with observability context
    with observe():
        try:
            logger.info(f"Planner Lambda invoked with event: {json.dumps(event)[:500]}")

            # Extract job_id from SQS message
            if 'Records' in event and len(event['Records']) > 0:
                # SQS message
                job_id = event['Records'][0]['body']
                if isinstance(job_id, str) and job_id.startswith('{'):
                    # Body might be JSON
                    try:
                        body = json.loads(job_id)
                        job_id = body.get('job_id', job_id)
                    except json.JSONDecodeError:
                        pass
            elif 'job_id' in event:
                # Direct invocation
                job_id = event['job_id']
            else:
                logger.error("No job_id found in event")
                return {
                    'statusCode': 400,
                    'body': json.dumps({'error': 'No job_id provided'})
                }

            logger.info(f"Planner: Starting orchestration for job {job_id}")

            # Idempotency guard: skip if this job is already running or completed
            job = db.jobs.find_by_id(job_id)
            if job:
                status = job.get('status')
                if status == 'completed':
                    logger.info(f"Planner: Job {job_id} already completed. Skipping re-run.")
                    return {
                        'statusCode': 200,
                        'body': json.dumps({
                            'success': True,
                            'message': f'Job {job_id} already completed'
                        })
                    }
                if status == 'running':
                    logger.info(f"Planner: Duplicate invocation detected for job {job_id} (already running). Skipping.")
                    return {
                        'statusCode': 200,
                        'body': json.dumps({
                            'success': True,
                            'message': f'Job {job_id} is already in progress'
                        })
                    }

            # Atomic lock: set job status to running if not already running/completed
            try:
                from botocore.exceptions import ClientError
                table = db.client.table('jobs')
                now_iso = datetime.utcnow().isoformat()
                table.update_item(
                    Key={'id': job_id},
                    UpdateExpression='SET #s = :running, updated_at = :t, started_at = if_not_exists(started_at, :t)',
                    ConditionExpression='attribute_not_exists(#s) OR #s = :pending',
                    ExpressionAttributeNames={'#s': 'status'},
                    ExpressionAttributeValues={':running': 'running', ':t': now_iso, ':pending': 'pending'}
                )
            except ClientError as e:
                if e.response.get('Error', {}).get('Code') == 'ConditionalCheckFailedException':
                    logger.info(f"Planner: Lock failed for job {job_id} (already running/completed). Skipping.")
                    return {
                        'statusCode': 200,
                        'body': json.dumps({
                            'success': True,
                            'message': f'Job {job_id} is already in progress or finished'
                        })
                    }
                else:
                    logger.error(f"Planner: Unexpected DynamoDB error acquiring lock: {str(e)}")
                    raise

            # Run the orchestrator
            asyncio.run(run_orchestrator(job_id))

            return {
                'statusCode': 200,
                'body': json.dumps({
                    'success': True,
                    'message': f'Analysis completed for job {job_id}'
                })
            }

        except Exception as e:
            logger.error(f"Planner: Error in lambda handler: {e}", exc_info=True)
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'success': False,
                    'error': str(e)
                })
            }

# For local testing
if __name__ == "__main__":
    # Define a test user
    test_user_id = "test_user_planner_local"

    # Ensure the test user exists before creating a job
    from src.schemas import UserCreate, JobCreate
    
    user = db.users.find_by_clerk_id(test_user_id)
    if not user:
        print(f"Creating test user: {test_user_id}")
        user_create = UserCreate(clerk_user_id=test_user_id, display_name="Test Planner User")
        db.users.create(user_create.model_dump(), returning='clerk_user_id')

    # Create a test job
    print("Creating test job...")
    job_create = JobCreate(
        clerk_user_id=test_user_id,
        job_type='portfolio_analysis',
        request_payload={
            'analysis_type': 'comprehensive',
            'test': True
        }
    )
    
    job = db.jobs.create(job_create.model_dump())
    job_id = job
    
    print(f"Created test job: {job_id}")
    
    # Test the handler
    test_event = {
        'job_id': job_id
    }
    
    result = lambda_handler(test_event, None)
    print(json.dumps(result, indent=2))