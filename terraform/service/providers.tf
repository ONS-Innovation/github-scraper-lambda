terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

terraform {
  backend "s3" {
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      "Project"       = var.project_tag
      "TeamOwner"     = var.team_owner_tag
      "BusinessOwner" = var.business_owner_tag
      "Service"       = "${var.project_tag}-ecs-infra"
      "Environment"   = var.domain
      "Terraform"     = "true"
    }
  }
}
