# VPC Connector Configuration for Dungeon Master Service
#
# This file provides Terraform configuration for creating a Serverless VPC Access connector
# to enable Cloud Run services to access resources on private VPC networks.
#
# Use Cases:
#   - Connecting to Cloud SQL instances with private IP
#   - Accessing internal services on VPC
#   - Compliance requirements for private network traffic
#
# Prerequisites:
#   - VPC network created (default network or custom)
#   - Sufficient IP address range available (minimum /28)
#   - Compute Engine API enabled
#
# Usage:
#   terraform init
#   terraform plan -out=plan.tfplan
#   terraform apply plan.tfplan
#
# References:
#   - https://cloud.google.com/vpc/docs/configure-serverless-vpc-access
#   - https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/vpc_access_connector

terraform {
  required_version = ">= 1.0, < 2.0"
  
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

# Variables
variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for VPC connector"
  type        = string
  default     = "us-central1"
}

variable "connector_name" {
  description = "Name of the VPC connector"
  type        = string
  default     = "dungeon-master-connector"
}

variable "network" {
  description = "VPC network name (default or custom)"
  type        = string
  default     = "default"
}

variable "ip_cidr_range" {
  description = "CIDR range for VPC connector (must be /28 and unused)"
  type        = string
  default     = "10.8.0.0/28"
}

variable "min_instances" {
  description = "Minimum number of connector instances"
  type        = number
  default     = 2
}

variable "max_instances" {
  description = "Maximum number of connector instances"
  type        = number
  default     = 10
}

variable "machine_type" {
  description = "Machine type for connector instances"
  type        = string
  default     = "e2-micro"
  
  validation {
    condition     = contains(["e2-micro", "e2-standard-4", "f1-micro"], var.machine_type)
    error_message = "Machine type must be one of: e2-micro, e2-standard-4, f1-micro"
  }
}

# Provider configuration
provider "google" {
  project = var.project_id
  region  = var.region
}

# Enable required APIs
resource "google_project_service" "vpcaccess" {
  project = var.project_id
  service = "vpcaccess.googleapis.com"
  
  disable_on_destroy = false
}

resource "google_project_service" "compute" {
  project = var.project_id
  service = "compute.googleapis.com"
  
  disable_on_destroy = false
}

# VPC Access Connector
resource "google_vpc_access_connector" "dungeon_master_connector" {
  name          = var.connector_name
  region        = var.region
  network       = var.network
  ip_cidr_range = var.ip_cidr_range
  
  min_instances = var.min_instances
  max_instances = var.max_instances
  machine_type  = var.machine_type
  
  depends_on = [
    google_project_service.vpcaccess,
    google_project_service.compute
  ]
}

# Outputs
output "connector_id" {
  description = "Full resource ID of the VPC connector"
  value       = google_vpc_access_connector.dungeon_master_connector.id
}

output "connector_name" {
  description = "Name of the VPC connector"
  value       = google_vpc_access_connector.dungeon_master_connector.name
}

output "connector_self_link" {
  description = "Self-link for the VPC connector (use in Cloud Run --vpc-connector flag)"
  value       = google_vpc_access_connector.dungeon_master_connector.self_link
}

output "usage_instructions" {
  description = "Instructions for using the VPC connector with Cloud Run"
  value       = <<-EOT
    To use this VPC connector with Cloud Run:
    
    # Via gcloud CLI:
    gcloud run services update dungeon-master \
      --vpc-connector ${google_vpc_access_connector.dungeon_master_connector.name} \
      --vpc-egress private-ranges-only \
      --region ${var.region}
    
    # In service.yaml:
    spec:
      template:
        metadata:
          annotations:
            run.googleapis.com/vpc-access-connector: ${google_vpc_access_connector.dungeon_master_connector.self_link}
            run.googleapis.com/vpc-access-egress: private-ranges-only
  EOT
}
