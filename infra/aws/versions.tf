terraform {
  required_version = "= 1.12.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.55.0"
    }
  }

  backend "s3" {
    bucket       = "example-tofu-state"
    key          = "factory/aws/tofu.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }

  encryption {
    key_provider "pbkdf2" "state_v1" {
      passphrase               = var.state_encryption_passphrase
      key_length               = 32
      iterations               = 600000
      hash_function            = "sha512"
      encrypted_metadata_alias = "patchyard-state-v1"
    }

    method "aes_gcm" "state_v1" {
      keys = key_provider.pbkdf2.state_v1
    }

    state {
      method   = method.aes_gcm.state_v1
      enforced = true
    }

    plan {
      method   = method.aes_gcm.state_v1
      enforced = true
    }
  }
}

variable "state_encryption_passphrase" {
  description = "Client-side state encryption passphrase supplied through the environment."
  type        = string
  sensitive   = true
  ephemeral   = true
}

variable "aws_provider_access_key_id" {
  description = "Route 53/IAM provider identity, kept distinct from the S3 backend identity."
  type        = string
  sensitive   = true
  ephemeral   = true
}

variable "aws_provider_secret_access_key" {
  description = "Route 53/IAM provider secret, supplied only through the environment."
  type        = string
  sensitive   = true
  ephemeral   = true
}

provider "aws" {
  region     = "us-east-1"
  access_key = var.aws_provider_access_key_id
  secret_key = var.aws_provider_secret_access_key
}
