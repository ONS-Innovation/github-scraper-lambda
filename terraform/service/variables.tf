# Default variables

variable "aws_account_id" {
  description = "AWS Account ID"
  type        = string
}

variable "aws_access_key_id" {
  description = "AWS Access Key ID"
  type        = string
}

variable "aws_secret_access_key" {
  description = "AWS Secret Access Key"
  type        = string
}

variable "service_subdomain" {
  description = "Service subdomain"
  type        = string
  default     = "github-scraper"
}

variable "domain" {
  description = "Domain"
  type        = string
  default     = "sdp-dev"
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = "eu-west-2"
}

variable "container_ver" {
  description = "Container tag"
  type        = string
  default     = "v0.0.1"
}

variable "project_tag" {
  description = "Project"
  type        = string
  default     = "GHA"
}

variable "team_owner_tag" {
  description = "Team Owner"
  type        = string
  default     = "Knowledge Exchange Hub"
}

variable "business_owner_tag" {
  description = "Business Owner"
  type        = string
  default     = "DST"
}

# EventBridge Lambda variables

variable "ecr_repository_name" {
  description = "Name of the ECR repository"
  type        = string
  default     = "sdp-dev-github-scraper"
}

variable "schedule" {
  description = "Schedule"
  type        = string
  default     = "cron(0 6 ? * MON,FRI *)"
}

variable "log_retention_days" {
  description = "Lambda log retention in days"
  type        = number
  default     = 7
}

variable "lambda_arch" {
  description = "Lambda architecture"
  type        = string
  default     = "arm64"
}


# Project specific variables

variable "source_bucket" {
  description = "Source S3 bucket name"
  type        = string
  default     = "sdp-dev-tech-radar"
}

variable "source_key" {
  description = "Source S3 key"
  type        = string
  default     = "repositories.json"
}

variable "github_app_client_id" {
  description = "Github App Client ID"
  type        = string
  sensitive   = true
}

variable "aws_secret_name" {
  description = "AWS Secret Name"
  type        = string
}

variable "github_org" {
  description = "Github Org"
  type        = string
}

variable "batch_size" {
  description = "Batch size when requesting repositories from Github"
  type        = number
  default     = 30
}
