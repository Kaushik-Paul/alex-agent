terraform {
  required_version = ">= 1.5"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  
  # Using local backend - state will be stored in terraform.tfstate in this directory
  # This is automatically gitignored for security
}

provider "aws" {
  region = var.aws_region
}

# Data sources
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  project = "alex"
  part    = "5"
}

# ========================================
# DynamoDB Tables (On-Demand)
# ========================================

resource "aws_dynamodb_table" "users" {
  name         = "${var.db_table_prefix}users"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "clerk_user_id"

  attribute {
    name = "clerk_user_id"
    type = "S"
  }

  tags = {
    Project = local.project
    Part    = local.part
  }
}

resource "aws_dynamodb_table" "instruments" {
  name         = "${var.db_table_prefix}instruments"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "symbol"

  attribute { name = "symbol"           type = "S" }
  attribute { name = "instrument_type"  type = "S" }

  global_secondary_index {
    name               = "instrument_type-index"
    hash_key           = "instrument_type"
    projection_type    = "ALL"
  }

  tags = {
    Project = local.project
    Part    = local.part
  }
}

resource "aws_dynamodb_table" "accounts" {
  name         = "${var.db_table_prefix}accounts"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute { name = "id"            type = "S" }
  attribute { name = "clerk_user_id" type = "S" }
  attribute { name = "created_at"    type = "S" }

  global_secondary_index {
    name               = "clerk_user_id-index"
    hash_key           = "clerk_user_id"
    range_key          = "created_at"
    projection_type    = "ALL"
  }

  tags = {
    Project = local.project
    Part    = local.part
  }
}

resource "aws_dynamodb_table" "positions" {
  name         = "${var.db_table_prefix}positions"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute { name = "id"         type = "S" }
  attribute { name = "account_id" type = "S" }
  attribute { name = "symbol"     type = "S" }

  global_secondary_index {
    name               = "account_id-symbol-index"
    hash_key           = "account_id"
    range_key          = "symbol"
    projection_type    = "ALL"
  }

  tags = {
    Project = local.project
    Part    = local.part
  }
}

resource "aws_dynamodb_table" "jobs" {
  name         = "${var.db_table_prefix}jobs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute { name = "id"            type = "S" }
  attribute { name = "clerk_user_id" type = "S" }
  attribute { name = "created_at"    type = "S" }

  global_secondary_index {
    name               = "user-index"
    hash_key           = "clerk_user_id"
    range_key          = "created_at"
    projection_type    = "ALL"
  }

  tags = {
    Project = local.project
    Part    = local.part
  }
}
