terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region     = "ap-south-1"
  access_key = "test"
  secret_key = "test"

  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
  skip_region_validation      = true

  endpoints {
    ec2 = "http://localhost:4566"
    eks = "http://localhost:4566"
    iam = "http://localhost:4566"
    sts = "http://localhost:4566"
  }
}

variable "vpc_id" {
  type = string
}

variable "vpc_cidr_block" {
  type = string
}

variable "control_plane_subnet_ids" {
  type = list(string)
}

variable "node_subnet_ids" {
  type = list(string)
}

module "eks" {
  source = "../modules/eks"

  cluster_name    = "servicedesk-eks"
  cluster_version = "1.33"

  vpc_id                   = var.vpc_id
  vpc_cidr_block           = var.vpc_cidr_block
  control_plane_subnet_ids = var.control_plane_subnet_ids
  node_subnet_ids          = var.node_subnet_ids

  node_group_name = "servicedesk-workers"

  create_cloudwatch_log_group = false
  cluster_addons              = []

  tags = {
    Project   = "servicedesk"
    ManagedBy = "terraform"
    Purpose   = "localstack-eks-capability-probe"
  }
}
