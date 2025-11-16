"""
Database models and query builders
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, date
from decimal import Decimal
import uuid
from boto3.dynamodb.conditions import Attr
from .client import DynamoClient
from .schemas import (
    InstrumentCreate, UserCreate, AccountCreate,
    PositionCreate, JobCreate, JobUpdate
)


class BaseModel:
    """Base class for database models (DynamoDB)"""

    table_name = None

    def __init__(self, db: DynamoClient):
        self.db = db
        if not self.table_name:
            raise ValueError("table_name must be defined")


class Users(BaseModel):
    """Users table operations"""
    table_name = 'users'
    
    def find_by_clerk_id(self, clerk_user_id: str) -> Optional[Dict]:
        """Find user by Clerk ID (primary key)"""
        return self.db.get_item(self.table_name, {"clerk_user_id": clerk_user_id})
    
    def create_user(self, clerk_user_id: str, display_name: str = None, 
                   years_until_retirement: int = None,
                   target_retirement_income: Decimal = None) -> str:
        """Create a new user"""
        now = datetime.utcnow().isoformat()
        item = {
            'clerk_user_id': clerk_user_id,
            'display_name': display_name,
            'years_until_retirement': years_until_retirement,
            'target_retirement_income': float(target_retirement_income) if target_retirement_income is not None else None,
            'asset_class_targets': {"equity": 70, "fixed_income": 30},
            'region_targets': {"north_america": 50, "international": 50},
            'created_at': now,
            'updated_at': now,
        }
        item = {k: v for k, v in item.items() if v is not None}
        self.db.put_item(self.table_name, item)
        return clerk_user_id

    def update_by_clerk_id(self, clerk_user_id: str, data: Dict) -> None:
        data = {k: v for k, v in data.items() if v is not None}
        data['updated_at'] = datetime.utcnow().isoformat()
        self.db.update_item(self.table_name, {"clerk_user_id": clerk_user_id}, data)


class Instruments(BaseModel):
    """Instruments table operations"""
    table_name = 'instruments'

    def find_all(self, limit: int = None, offset: int = 0) -> List[Dict]:
        """Scan instruments - no limit by default for autocomplete"""
        return self.db.scan(self.table_name, limit=limit)

    def find_by_symbol(self, symbol: str) -> Optional[Dict]:
        """Find instrument by symbol (primary key)"""
        return self.db.get_item(self.table_name, {"symbol": symbol})
    
    def create_instrument(self, instrument: InstrumentCreate) -> str:
        """Create a new instrument with validation"""
        # Validate using Pydantic
        validated = instrument.model_dump()
        
        now = datetime.utcnow().isoformat()
        item = {
            'symbol': validated['symbol'],
            'name': validated['name'],
            'instrument_type': validated['instrument_type'],
            'current_price': float(validated.get('current_price', 0)) if validated.get('current_price') is not None else None,
            'allocation_regions': validated['allocation_regions'],
            'allocation_sectors': validated['allocation_sectors'],
            'allocation_asset_class': validated['allocation_asset_class'],
            'created_at': now,
            'updated_at': now,
        }
        item = {k: v for k, v in item.items() if v is not None}
        self.db.put_item(self.table_name, item)
        return validated['symbol']
    
    def find_by_type(self, instrument_type: str) -> List[Dict]:
        """Find all instruments of a specific type using GSI instrument_type-index"""
        return self.db.query_gsi_eq(self.table_name, "instrument_type-index", "instrument_type", instrument_type)
    
    def search(self, query: str) -> List[Dict]:
        """Search instruments by symbol or name (scan + filter contains)"""
        # DynamoDB doesn't support LIKE. Use contains filter via scan.
        # Note: Case-sensitive; for simplicity keep as-is.
        # For production, consider maintaining a lowercase field for search.
        items = self.db.scan(self.table_name)
        q = query.strip()
        res = [i for i in items if (i.get('symbol') and q in i['symbol']) or (i.get('name') and q.lower() in i['name'].lower())]
        return res[:20]


class Accounts(BaseModel):
    """Accounts table operations"""
    table_name = 'accounts'
    
    def find_by_user(self, clerk_user_id: str) -> List[Dict]:
        """Find all accounts for a user using GSI clerk_user_id-index"""
        items = self.db.query_gsi_eq(self.table_name, "clerk_user_id-index", "clerk_user_id", clerk_user_id, scan_index_forward=False)
        # Already sorted by created_at desc if used as sort key. If not, sort here.
        items.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        return items
    
    def create_account(self, clerk_user_id: str, account_name: str,
                      account_purpose: str = None, cash_balance: Decimal = Decimal('0'),
                      cash_interest: Decimal = Decimal('0')) -> str:
        """Create a new account"""
        now = datetime.utcnow().isoformat()
        account_id = str(uuid.uuid4())
        item = {
            'id': account_id,
            'clerk_user_id': clerk_user_id,
            'account_name': account_name,
            'account_purpose': account_purpose,
            'cash_balance': float(cash_balance) if cash_balance is not None else 0.0,
            'cash_interest': float(cash_interest) if cash_interest is not None else 0.0,
            'created_at': now,
            'updated_at': now,
        }
        item = {k: v for k, v in item.items() if v is not None}
        self.db.put_item(self.table_name, item)
        return account_id

    def find_by_id(self, account_id: str) -> Optional[Dict]:
        return self.db.get_item(self.table_name, {"id": account_id})

    def update(self, account_id: str, data: Dict) -> None:
        data = {k: v for k, v in data.items() if v is not None}
        data['updated_at'] = datetime.utcnow().isoformat()
        self.db.update_item(self.table_name, {"id": account_id}, data)

    def delete(self, account_id: str) -> None:
        self.db.delete_item(self.table_name, {"id": account_id})


class Positions(BaseModel):
    """Positions table operations"""
    table_name = 'positions'
    
    def find_by_account(self, account_id: str) -> List[Dict]:
        """Find all positions in an account via GSI account_id-symbol-index"""
        items = self.db.query_gsi_eq(self.table_name, "account_id-symbol-index", "account_id", account_id)
        items.sort(key=lambda x: x.get('symbol', ''))
        return items
    
    def get_portfolio_value(self, account_id: str) -> Dict:
        """Calculate total portfolio value by joining in code against instruments"""
        positions = self.find_by_account(account_id)
        num_positions = len({p.get('symbol') for p in positions})
        total_shares = 0.0
        total_value = 0.0
        for p in positions:
            qty = float(p.get('quantity', 0) or 0)
            total_shares += qty
            # Look up instrument price
            # Note: Import here to avoid circular import
            from .models import Instruments  # type: ignore
            inst_model = Instruments(self.db)
            inst = inst_model.find_by_symbol(p.get('symbol'))
            price = float(inst.get('current_price', 0) or 0) if inst else 0.0
            total_value += qty * price
        return {'num_positions': num_positions, 'total_value': total_value, 'total_shares': total_shares}
    
    def add_position(self, account_id: str, symbol: str, quantity: Decimal) -> str:
        """Add or update a position (upsert by account_id+symbol)"""
        # Try to find existing by account_id via GSI and filter by exact symbol
        items = self.db.query_gsi_eq(
            self.table_name,
            "account_id-symbol-index",
            "account_id",
            account_id,
            sk_name="symbol",
            sk_eq=symbol,
        )
        now = datetime.utcnow().isoformat()
        if items:
            pos = items[0]
            pos_id = pos['id']
            self.db.update_item(self.table_name, {"id": pos_id}, {
                "quantity": float(quantity),
                "as_of_date": date.today().isoformat(),
                "updated_at": now,
            })
            return pos_id
        else:
            pos_id = str(uuid.uuid4())
            item = {
                'id': pos_id,
                'account_id': account_id,
                'symbol': symbol,
                'quantity': float(quantity),
                'as_of_date': date.today().isoformat(),
                'created_at': now,
                'updated_at': now,
            }
            self.db.put_item(self.table_name, item)
            return pos_id

    def find_by_id(self, position_id: str) -> Optional[Dict]:
        return self.db.get_item(self.table_name, {"id": position_id})

    def update(self, position_id: str, data: Dict) -> None:
        data = {k: v for k, v in data.items() if v is not None}
        data['updated_at'] = datetime.utcnow().isoformat()
        self.db.update_item(self.table_name, {"id": position_id}, data)

    def delete(self, position_id: str) -> None:
        self.db.delete_item(self.table_name, {"id": position_id})


class Jobs(BaseModel):
    """Jobs table operations"""
    table_name = 'jobs'
    
    def create(self, data: Dict) -> str:
        """Compatibility: create a job from dict like tests expect"""
        return self.create_job(
            data.get('clerk_user_id'),
            data.get('job_type'),
            data.get('request_payload')
        )

    def create_job(self, clerk_user_id: str, job_type: str, 
                  request_payload: Dict = None) -> str:
        """Create a new job"""
        job_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        item = {
            'id': job_id,
            'clerk_user_id': clerk_user_id,
            'job_type': job_type,
            'status': 'pending',
            'request_payload': request_payload,
            'created_at': now,
            'updated_at': now,
        }
        self.db.put_item(self.table_name, item)
        return job_id
    
    def update_status(self, job_id: str, status: str, error_message: str = None) -> int:
        """Update job status"""
        data = {'status': status, 'updated_at': datetime.utcnow().isoformat()}
        if status == 'running':
            data['started_at'] = datetime.utcnow().isoformat()
        elif status in ['completed', 'failed']:
            data['completed_at'] = datetime.utcnow().isoformat()
        if error_message:
            data['error_message'] = error_message
        self.db.update_item(self.table_name, {"id": job_id}, data)
        return 1
    
    def update_report(self, job_id: str, report_payload: Dict) -> int:
        """Update job with Reporter agent's analysis"""
        self.db.update_item(self.table_name, {"id": job_id}, {"report_payload": report_payload, "updated_at": datetime.utcnow().isoformat()})
        return 1
    
    def update_charts(self, job_id: str, charts_payload: Dict) -> int:
        """Update job with Charter agent's visualization data"""
        self.db.update_item(self.table_name, {"id": job_id}, {"charts_payload": charts_payload, "updated_at": datetime.utcnow().isoformat()})
        return 1
    
    def update_retirement(self, job_id: str, retirement_payload: Dict) -> int:
        """Update job with Retirement agent's projections"""
        self.db.update_item(self.table_name, {"id": job_id}, {"retirement_payload": retirement_payload, "updated_at": datetime.utcnow().isoformat()})
        return 1
    
    def update_summary(self, job_id: str, summary_payload: Dict) -> int:
        """Update job with Planner's final summary"""
        self.db.update_item(self.table_name, {"id": job_id}, {"summary_payload": summary_payload, "updated_at": datetime.utcnow().isoformat()})
        return 1
    
    def find_by_user(self, clerk_user_id: str, status: str = None, 
                    limit: int = 20) -> List[Dict]:
        """Find jobs for a user using GSI user-index (PK clerk_user_id, SK created_at)"""
        items = self.db.query_gsi_eq(self.table_name, "user-index", "clerk_user_id", clerk_user_id, scan_index_forward=False)
        if status:
            items = [i for i in items if i.get('status') == status]
        return items[:limit]

    def find_by_id(self, job_id: str) -> Optional[Dict]:
        return self.db.get_item(self.table_name, {"id": job_id})

    def delete(self, job_id: str) -> None:
        """Compatibility: delete job by id"""
        self.db.delete_item(self.table_name, {"id": job_id})


class Database:
    """Main database interface providing access to all models (DynamoDB)"""

    def __init__(self, table_prefix: str = None, region: str = None):
        self.client = DynamoClient(table_prefix=table_prefix, region_name=region)

        # Initialize all models
        self.users = Users(self.client)
        self.instruments = Instruments(self.client)
        self.accounts = Accounts(self.client)
        self.positions = Positions(self.client)
        self.jobs = Jobs(self.client)