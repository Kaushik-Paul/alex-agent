"""
DynamoDB Client Wrapper
Provides a simple interface for database operations used by models
"""

import boto3
import json
import os
from typing import Dict, Any, Optional, List
from datetime import datetime, date
from decimal import Decimal
from botocore.exceptions import ClientError
import logging
from boto3.dynamodb.conditions import Key, Attr

# Try to load .env file if it exists
try:
    from dotenv import load_dotenv

    load_dotenv(override=True)
except ImportError:
    pass  # dotenv not installed, continue without it

logger = logging.getLogger(__name__)


class DynamoClient:
    """Lightweight DynamoDB helper used by the Database models"""

    def __init__(
        self,
        table_prefix: Optional[str] = None,
        region_name: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        table_names: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Initialize DynamoDB client

        Args:
            table_prefix: Optional prefix for table names, from env DB_TABLE_PREFIX (default: "alex_")
            region_name: AWS region, from env DEFAULT_AWS_REGION
            endpoint_url: Optional local/test endpoint
            table_names: Explicit table names override, e.g. {"users": "alex_users", ...}
        """
        self.region = region_name or os.environ.get("DEFAULT_AWS_REGION", "us-east-1")
        self.resource = boto3.resource("dynamodb", region_name=self.region, endpoint_url=endpoint_url)

        prefix = (table_prefix if table_prefix is not None else os.environ.get("DB_TABLE_PREFIX", "alex_")).strip()
        self.tables: Dict[str, str] = {
            "users": f"{prefix}users",
            "instruments": f"{prefix}instruments",
            "accounts": f"{prefix}accounts",
            "positions": f"{prefix}positions",
            "jobs": f"{prefix}jobs",
        }
        if table_names:
            self.tables.update(table_names)

    def table(self, logical_name: str):
        """Return a boto3 Table by logical name (users, instruments, accounts, positions, jobs)"""
        return self.resource.Table(self.tables[logical_name])

    # -------------------------
    # Basic item operations
    # -------------------------
    def put_item(self, logical_table: str, item: Dict[str, Any]) -> None:
        self.table(logical_table).put_item(Item=self._encode_item(item))

    def get_item(self, logical_table: str, key: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        resp = self.table(logical_table).get_item(Key=key)
        return self._decode_item(resp.get("Item")) if resp.get("Item") else None

    def delete_item(self, logical_table: str, key: Dict[str, Any]) -> None:
        self.table(logical_table).delete_item(Key=key)

    def update_item(self, logical_table: str, key: Dict[str, Any], data: Dict[str, Any]) -> None:
        if not data:
            return
        update_expr_parts = []
        expr_vals: Dict[str, Any] = {}
        expr_names: Dict[str, str] = {}
        for i, (k, v) in enumerate(data.items(), start=1):
            placeholder = f":v{i}"
            name_placeholder = f"#n{i}"
            update_expr_parts.append(f"{name_placeholder} = {placeholder}")
            expr_vals[placeholder] = self._encode_value(v)
            expr_names[name_placeholder] = k

        update_expr = "SET " + ", ".join(update_expr_parts)
        self.table(logical_table).update_item(
            Key=key,
            UpdateExpression=update_expr,
            ExpressionAttributeValues=expr_vals,
            ExpressionAttributeNames=expr_names,
        )

    # -------------------------
    # Query helpers
    # -------------------------
    def query_by_pk(self, logical_table: str, pk_name: str, pk_value: Any, sk_name: Optional[str] = None, sk_begins_with: Optional[str] = None, limit: Optional[int] = None, scan_index_forward: Optional[bool] = None) -> List[Dict[str, Any]]:
        tbl = self.table(logical_table)
        key_cond = Key(pk_name).eq(pk_value)
        if sk_name and sk_begins_with:
            key_cond &= Key(sk_name).begins_with(sk_begins_with)
        kwargs = {"KeyConditionExpression": key_cond}
        if limit:
            kwargs["Limit"] = limit
        if scan_index_forward is not None:
            kwargs["ScanIndexForward"] = scan_index_forward
        resp = tbl.query(**kwargs)
        return [self._decode_item(i) for i in resp.get("Items", [])]

    def query_gsi_eq(self, logical_table: str, index_name: str, key_name: str, key_value: Any, sk_name: Optional[str] = None, begins_with: Optional[str] = None, sk_eq: Optional[Any] = None, limit: Optional[int] = None, scan_index_forward: Optional[bool] = None, filter_expression: Optional[Any] = None) -> List[Dict[str, Any]]:
        tbl = self.table(logical_table)
        key_cond = Key(key_name).eq(key_value)
        if sk_name and sk_eq is not None:
            key_cond &= Key(sk_name).eq(sk_eq)
        elif sk_name and begins_with:
            key_cond &= Key(sk_name).begins_with(begins_with)
        kwargs = {"IndexName": index_name, "KeyConditionExpression": key_cond}
        if filter_expression is not None:
            kwargs["FilterExpression"] = filter_expression
        if limit:
            kwargs["Limit"] = limit
        if scan_index_forward is not None:
            kwargs["ScanIndexForward"] = scan_index_forward
        resp = tbl.query(**kwargs)
        return [self._decode_item(i) for i in resp.get("Items", [])]

    def query_gsi_between(self, logical_table: str, index_name: str, key_name: str, key_value: Any, sk_name: str, sk_start: Any, sk_end: Any, limit: Optional[int] = None, scan_index_forward: Optional[bool] = None, filter_expression: Optional[Any] = None) -> List[Dict[str, Any]]:
        """Query a GSI with partition key equality and sort key BETWEEN.

        Args:
            logical_table: Logical table name
            index_name: GSI name
            key_name: Partition key attribute name in the index
            key_value: Partition key value
            sk_name: Sort key attribute name in the index
            sk_start: Start value for BETWEEN (inclusive)
            sk_end: End value for BETWEEN (inclusive)
            limit: Optional max items to return
            scan_index_forward: Optional order
            filter_expression: Optional non-key FilterExpression
        """
        tbl = self.table(logical_table)
        key_cond = Key(key_name).eq(key_value) & Key(sk_name).between(sk_start, sk_end)
        kwargs: Dict[str, Any] = {"IndexName": index_name, "KeyConditionExpression": key_cond}
        if filter_expression is not None:
            kwargs["FilterExpression"] = filter_expression
        if limit:
            kwargs["Limit"] = limit
        if scan_index_forward is not None:
            kwargs["ScanIndexForward"] = scan_index_forward
        resp = tbl.query(**kwargs)
        return [self._decode_item(i) for i in resp.get("Items", [])]

    def scan(self, logical_table: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        tbl = self.table(logical_table)
        kwargs: Dict[str, Any] = {}
        if limit:
            kwargs["Limit"] = limit
        resp = tbl.scan(**kwargs)
        return [self._decode_item(i) for i in resp.get("Items", [])]

    # -------------------------
    # Encoding helpers
    # -------------------------
    def _encode_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        return {k: self._encode_value(v) for k, v in item.items()}

    def _encode_scalar(self, value: Any) -> Any:
        # DynamoDB requires Decimal for numeric types
        from decimal import Decimal as _D
        if isinstance(value, (int, _D)):
            return value if isinstance(value, _D) else _D(value)
        if isinstance(value, float):
            return _D(str(value))
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        return value

    def _encode_value(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {k: self._encode_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._encode_value(v) for v in value]
        return self._encode_scalar(value)

    def _decode_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        from decimal import Decimal as _D
        def _convert(v: Any) -> Any:
            if isinstance(v, dict):
                return {k: _convert(x) for k, x in v.items()}
            if isinstance(v, list):
                return [_convert(x) for x in v]
            if isinstance(v, _D):
                # Preserve ints precisely
                if v == v.to_integral_value():
                    try:
                        return int(v)
                    except Exception:
                        return float(v)
                try:
                    return float(v)
                except Exception:
                    return str(v)
            return v
        return _convert(item)

    # Backward-compat placeholders (no-ops) so existing callers won't break if mistakenly used
    def execute(self, *_args, **_kwargs):
        raise NotImplementedError("execute() is not supported for DynamoDB")

    def query(self, *_args, **_kwargs):
        raise NotImplementedError("query(sql) is not supported for DynamoDB")

    def query_one(self, *_args, **_kwargs):
        raise NotImplementedError("query_one(sql) is not supported for DynamoDB")

    def insert(self, *_args, **_kwargs):
        raise NotImplementedError("insert(sql) is not supported for DynamoDB")

    def update(self, *_args, **_kwargs):
        raise NotImplementedError("update(sql) is not supported for DynamoDB")

    def delete(self, *_args, **_kwargs):
        raise NotImplementedError("delete(sql) is not supported for DynamoDB")

    def begin_transaction(self, *_args, **_kwargs):
        raise NotImplementedError("Transactions are not supported in DynamoDB client")

    def commit_transaction(self, *_args, **_kwargs):
        raise NotImplementedError("Transactions are not supported in DynamoDB client")

    def rollback_transaction(self, *_args, **_kwargs):
        raise NotImplementedError("Transactions are not supported in DynamoDB client")

    def _build_parameters(self, *_args, **_kwargs):
        raise NotImplementedError

    def _extract_value(self, *_args, **_kwargs):
        raise NotImplementedError
