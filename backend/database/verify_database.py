#!/usr/bin/env python3
"""
Comprehensive database verification for DynamoDB
Shows tables, counts, sample instruments, and validates allocation sums
"""

import os
from dotenv import load_dotenv
from src import Database

load_dotenv(override=True)

def main():
    print("🔍 DATABASE VERIFICATION REPORT (DynamoDB)")
    print("=" * 70)
    print(f"📍 Region: {os.getenv('DEFAULT_AWS_REGION', 'us-east-1')}")
    print(f"🏷️  Table prefix: {os.getenv('DB_TABLE_PREFIX', 'alex_')}")
    print("=" * 70)

    db = Database()

    # 1. Count records in each table
    print("\n📈 RECORD COUNTS PER TABLE\n")
    tables = [
        ("users", db.users),
        ("instruments", db.instruments),
        ("accounts", db.accounts),
        ("positions", db.positions),
        ("jobs", db.jobs),
    ]
    for name, model in tables:
        try:
            # Use scan for counts (small data set assumption)
            items = model.db.scan(name)
            count = len(items)
            status = "✅" if (name == 'instruments' and count > 0) else "📭"
            print(f"   {status} {name:<20} {count:,} records")
        except Exception as e:
            print(f"   ❌ {name:<20} error: {e}")

    # 2. Sample instruments
    try:
        instruments = db.instruments.find_all(limit=10)
        print("\n🎯 SAMPLE INSTRUMENTS (First 10)")
        print("Symbol | Name | Type | Asset Class Allocation")
        print("-" * 70)
        for inst in instruments:
            print(f"{inst.get('symbol', ''):<6} | {str(inst.get('name', ''))[:35]:<35} | {inst.get('instrument_type', ''):<10} | {inst.get('allocation_asset_class', {})}")
    except Exception as e:
        print(f"   ❌ Error listing instruments: {e}")

    # 3. Validate allocation sums for a sample set
    print("\n✅ ALLOCATION VALIDATION (Sample)")
    for sym in ["SPY", "QQQ", "BND", "VEA", "GLD"]:
        inst = db.instruments.find_by_symbol(sym)
        if not inst:
            print(f"   ⚠️  {sym}: Not found")
            continue
        regions = inst.get('allocation_regions', {})
        sectors = inst.get('allocation_sectors', {})
        assets = inst.get('allocation_asset_class', {})
        rs = sum(regions.values()) if isinstance(regions, dict) else 0
        ss = sum(sectors.values()) if isinstance(sectors, dict) else 0
        as_ = sum(assets.values()) if isinstance(assets, dict) else 0
        ok = (abs(rs-100) <= 3) and (abs(ss-100) <= 3) and (abs(as_-100) <= 3)
        status = "✅ Valid" if ok else "❌ Invalid"
        print(f"   {sym:<6} | Regions: {rs:>6.1f}% | Sectors: {ss:>6.1f}% | Assets: {as_:>6.1f}% | {status}")

    print("\n" + "=" * 70)
    print("🎉 DYNAMODB VERIFICATION COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    main()