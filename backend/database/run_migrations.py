#!/usr/bin/env python3
"""
Simple migration/verification for DynamoDB
Ensures required tables and GSIs exist (idempotent)
"""

import os
import time
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv(override=True)

region = os.environ.get("DEFAULT_AWS_REGION", "us-east-1")
prefix = os.environ.get("DB_TABLE_PREFIX", "alex_")

dynamodb = boto3.client("dynamodb", region_name=region)

def table_exists(name: str) -> bool:
    try:
        dynamodb.describe_table(TableName=name)
        return True
    except dynamodb.exceptions.ResourceNotFoundException:
        return False

def ensure_gsi(table_name: str, gsi_def: dict):
    try:
        desc = dynamodb.describe_table(TableName=table_name)
        existing = {g["IndexName"] for g in desc["Table"].get("GlobalSecondaryIndexes", [])}
        if gsi_def["IndexName"] in existing:
            return
        print(f"   • Creating GSI {gsi_def['IndexName']} on {table_name}...")
        dynamodb.update_table(
            TableName=table_name,
            AttributeDefinitions=gsi_def.pop("AttributeDefinitions"),
            GlobalSecondaryIndexUpdates=[{"Create": gsi_def}],
        )
        # Wait for ACTIVE
        while True:
            time.sleep(2)
            status = dynamodb.describe_table(TableName=table_name)["Table"]["TableStatus"]
            if status == "ACTIVE":
                break
    except ClientError as e:
        print(f"     ⚠️  Could not ensure GSI {gsi_def.get('IndexName')}: {e.response['Error']['Message']}")

def ensure_table_users():
    name = f"{prefix}users"
    if table_exists(name):
        print(f"✅ {name} exists")
        return
    print(f"Creating {name}...")
    dynamodb.create_table(
        TableName=name,
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[{"AttributeName": "clerk_user_id", "AttributeType": "S"}],
        KeySchema=[{"AttributeName": "clerk_user_id", "KeyType": "HASH"}],
    )

def ensure_table_instruments():
    name = f"{prefix}instruments"
    if not table_exists(name):
        print(f"Creating {name}...")
        dynamodb.create_table(
            TableName=name,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": "symbol", "AttributeType": "S"},
                {"AttributeName": "instrument_type", "AttributeType": "S"},
            ],
            KeySchema=[{"AttributeName": "symbol", "KeyType": "HASH"}],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "instrument_type-index",
                    "KeySchema": [{"AttributeName": "instrument_type", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                    "ProvisionedThroughput": {"ReadCapacityUnits": 1, "WriteCapacityUnits": 1},
                }
            ],
            ProvisionedThroughput={"ReadCapacityUnits": 1, "WriteCapacityUnits": 1},
        )
    else:
        # Ensure GSI exists
        ensure_gsi(
            name,
            {
                "IndexName": "instrument_type-index",
                "KeySchema": [{"AttributeName": "instrument_type", "KeyType": "HASH"}],
                "Projection": {"ProjectionType": "ALL"},
                "ProvisionedThroughput": {"ReadCapacityUnits": 1, "WriteCapacityUnits": 1},
                "AttributeDefinitions": [{"AttributeName": "instrument_type", "AttributeType": "S"}],
            },
        )

def ensure_table_accounts():
    name = f"{prefix}accounts"
    if not table_exists(name):
        print(f"Creating {name}...")
        dynamodb.create_table(
            TableName=name,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": "id", "AttributeType": "S"},
                {"AttributeName": "clerk_user_id", "AttributeType": "S"},
                {"AttributeName": "created_at", "AttributeType": "S"},
            ],
            KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "clerk_user_id-index",
                    "KeySchema": [
                        {"AttributeName": "clerk_user_id", "KeyType": "HASH"},
                        {"AttributeName": "created_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                    "ProvisionedThroughput": {"ReadCapacityUnits": 1, "WriteCapacityUnits": 1},
                }
            ],
            ProvisionedThroughput={"ReadCapacityUnits": 1, "WriteCapacityUnits": 1},
        )
    else:
        ensure_gsi(
            name,
            {
                "IndexName": "clerk_user_id-index",
                "KeySchema": [
                    {"AttributeName": "clerk_user_id", "KeyType": "HASH"},
                    {"AttributeName": "created_at", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
                "ProvisionedThroughput": {"ReadCapacityUnits": 1, "WriteCapacityUnits": 1},
                "AttributeDefinitions": [
                    {"AttributeName": "clerk_user_id", "AttributeType": "S"},
                    {"AttributeName": "created_at", "AttributeType": "S"},
                ],
            },
        )

def ensure_table_positions():
    name = f"{prefix}positions"
    if not table_exists(name):
        print(f"Creating {name}...")
        dynamodb.create_table(
            TableName=name,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": "id", "AttributeType": "S"},
                {"AttributeName": "account_id", "AttributeType": "S"},
                {"AttributeName": "symbol", "AttributeType": "S"},
            ],
            KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "account_id-symbol-index",
                    "KeySchema": [
                        {"AttributeName": "account_id", "KeyType": "HASH"},
                        {"AttributeName": "symbol", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                    "ProvisionedThroughput": {"ReadCapacityUnits": 1, "WriteCapacityUnits": 1},
                }
            ],
            ProvisionedThroughput={"ReadCapacityUnits": 1, "WriteCapacityUnits": 1},
        )
    else:
        ensure_gsi(
            name,
            {
                "IndexName": "account_id-symbol-index",
                "KeySchema": [
                    {"AttributeName": "account_id", "KeyType": "HASH"},
                    {"AttributeName": "symbol", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
                "ProvisionedThroughput": {"ReadCapacityUnits": 1, "WriteCapacityUnits": 1},
                "AttributeDefinitions": [
                    {"AttributeName": "account_id", "AttributeType": "S"},
                    {"AttributeName": "symbol", "AttributeType": "S"},
                ],
            },
        )

def ensure_table_jobs():
    name = f"{prefix}jobs"
    if not table_exists(name):
        print(f"Creating {name}...")
        dynamodb.create_table(
            TableName=name,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": "id", "AttributeType": "S"},
                {"AttributeName": "clerk_user_id", "AttributeType": "S"},
                {"AttributeName": "created_at", "AttributeType": "S"},
            ],
            KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "user-index",
                    "KeySchema": [
                        {"AttributeName": "clerk_user_id", "KeyType": "HASH"},
                        {"AttributeName": "created_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                    "ProvisionedThroughput": {"ReadCapacityUnits": 1, "WriteCapacityUnits": 1},
                }
            ],
            ProvisionedThroughput={"ReadCapacityUnits": 1, "WriteCapacityUnits": 1},
        )
    else:
        ensure_gsi(
            name,
            {
                "IndexName": "user-index",
                "KeySchema": [
                    {"AttributeName": "clerk_user_id", "KeyType": "HASH"},
                    {"AttributeName": "created_at", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
                "ProvisionedThroughput": {"ReadCapacityUnits": 1, "WriteCapacityUnits": 1},
                "AttributeDefinitions": [
                    {"AttributeName": "clerk_user_id", "AttributeType": "S"},
                    {"AttributeName": "created_at", "AttributeType": "S"},
                ],
            },
        )

print("🚀 Ensuring DynamoDB tables and indexes...")
print("=" * 50)

for ensure in [
    ensure_table_users,
    ensure_table_instruments,
    ensure_table_accounts,
    ensure_table_positions,
    ensure_table_jobs,
]:
    try:
        ensure()
    except ClientError as e:
        print(f"❌ Error: {e.response['Error']['Message']}")

print("\n✅ Migration/verification complete.")
print("\n📝 Next steps:")
print("1. Load seed data: uv run seed_data.py")
print("2. Test database operations: uv run test_db.py")
