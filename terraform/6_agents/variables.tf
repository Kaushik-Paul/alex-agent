variable "aws_region" {
  description = "AWS region for resources"
  type        = string
}

variable "db_table_prefix" {
  description = "Prefix for DynamoDB tables (from Part 5 outputs)"
  type        = string
  default     = "alex_"
}

variable "vector_bucket" {
  description = "S3 Vectors bucket name from Part 3"
  type        = string
}

variable "bedrock_model_id" {
  description = "Bedrock model ID to use for agents"
  type        = string
}

variable "bedrock_region" {
  description = "AWS region for Bedrock"
  type        = string
}

variable "sagemaker_endpoint" {
  description = "SageMaker endpoint name from Part 2"
  type        = string
  default     = "alex-embedding-endpoint"
}

variable "polygon_api_key" {
  description = "Polygon.io API key for market data"
  type        = string
}

variable "polygon_plan" {
  description = "Polygon.io plan type (free or paid)"
  type        = string
  default     = "free"
}

# LangFuse observability variables (optional)
variable "langfuse_public_key" {
  description = "LangFuse public key for observability (optional)"
  type        = string
  default     = ""
  sensitive   = false
}

variable "langfuse_secret_key" {
  description = "LangFuse secret key for observability (optional)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "langfuse_host" {
  description = "LangFuse host URL (optional)"
  type        = string
  default     = "https://us.cloud.langfuse.com"
}

# OpenAI API key for tracing (required for OpenAI Agents SDK tracing)
variable "openai_api_key" {
  description = "OpenAI API key for enabling tracing in OpenAI Agents SDK"
  type        = string
  default     = ""
  sensitive   = true
}

variable "openrouter_api_key" {
  description = "Openrouter API key for market data"
  type        = string
}

variable "openrouter_model_id" {
  description = "Openrouter model id for market data"
  type        = string
}

variable "tagger_max_per_call" {
  description = "Max instrument call for tagger agent"
  type = number
}

variable "orchestrator_mode" {
  description = "More deterministic planner to prevent LLM loops"
  type = string
}

variable "tagger_batch_mode" {
  description = "Calls tagger agent in batch mode"
  type = string
}