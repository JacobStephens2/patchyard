terraform {
  required_version = "= 1.12.0"

  required_providers {
    digitalocean = {
      source  = "digitalocean/digitalocean"
      version = "= 2.95.0"
    }
  }

  backend "s3" {
    bucket       = "example-tofu-state"
    key          = "factory/digitalocean/tofu.tfstate"
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
  description = "Client-side state encryption passphrase, supplied only through TF_VAR_state_encryption_passphrase."
  type        = string
  sensitive   = true
  ephemeral   = true
}

provider "digitalocean" {}
