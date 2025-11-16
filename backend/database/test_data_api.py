#!/usr/bin/env python3
"""
Test DynamoDB Connectivity
Verifies that expected tables exist and are accessible with the configured prefix.
"""

import boto3
import os
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv(override=True)

def main():
    print("🚀 DynamoDB Connectivity Test")
    print("=" * 50)

    region = os.getenv('DEFAULT_AWS_REGION', 'us-east-1')
    prefix = os.getenv('DB_TABLE_PREFIX', 'alex_')
    print(f"📍 Using AWS Region: {region}")
    print(f"🏷️  Table prefix: {prefix}")

    client = boto3.client('dynamodb', region_name=region)
    expected = [f"{prefix}users", f"{prefix}instruments", f"{prefix}accounts", f"{prefix}positions", f"{prefix}jobs"]

    ok = True
    for table in expected:
        try:
            desc = client.describe_table(TableName=table)
            status = desc['Table']['TableStatus']
            print(f"   ✅ {table} - {status}")
        except client.exceptions.ResourceNotFoundException:
            print(f"   ❌ {table} not found")
            ok = False
        except ClientError as e:
            print(f"   ❌ Error checking {table}: {e}")
            ok = False

    print("\n" + ("✅ DynamoDB is configured correctly!" if ok else "⚠️  Some tables are missing. Run: uv run run_migrations.py"))

if __name__ == "__main__":
    main()