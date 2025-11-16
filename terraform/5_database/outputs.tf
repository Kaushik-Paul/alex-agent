output "db_table_prefix" {
  description = "Prefix for DynamoDB tables"
  value       = var.db_table_prefix
}

output "users_table_arn" {
  description = "ARN of DynamoDB users table"
  value       = aws_dynamodb_table.users.arn
}

output "instruments_table_arn" {
  description = "ARN of DynamoDB instruments table"
  value       = aws_dynamodb_table.instruments.arn
}

output "accounts_table_arn" {
  description = "ARN of DynamoDB accounts table"
  value       = aws_dynamodb_table.accounts.arn
}

output "positions_table_arn" {
  description = "ARN of DynamoDB positions table"
  value       = aws_dynamodb_table.positions.arn
}

output "jobs_table_arn" {
  description = "ARN of DynamoDB jobs table"
  value       = aws_dynamodb_table.jobs.arn
}

output "setup_instructions" {
  description = "Instructions for setting up the database"
  value = <<-EOT
    
    ✅ DynamoDB tables deployed successfully!
    
    Tables (prefix: ${var.db_table_prefix}):
    - Users:       ${aws_dynamodb_table.users.name}
    - Instruments: ${aws_dynamodb_table.instruments.name}
    - Accounts:    ${aws_dynamodb_table.accounts.name}
    - Positions:   ${aws_dynamodb_table.positions.name}
    - Jobs:        ${aws_dynamodb_table.jobs.name}
    
    Add the following to your .env file (used by backend and agents):
    DB_TABLE_PREFIX=${var.db_table_prefix}
    DEFAULT_AWS_REGION=${data.aws_region.current.name}
    
    Initialize tables (idempotent):
    cd backend/database
    uv run run_migrations.py
    
    Load seed data:
    uv run seed_data.py
    
    💰 Cost Management:
    - Using PAY_PER_REQUEST billing mode (on-demand)
    - Tables scale automatically with usage; near-zero idle cost
  EOT
}