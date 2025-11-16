variable "aws_region" {
  description = "AWS region for resources"
  type        = string
}

variable "db_table_prefix" {
  description = "Prefix for DynamoDB table names"
  type        = string
  default     = "alex_"
}