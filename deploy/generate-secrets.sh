#!/bin/sh
# Prints fresh random values for the secrets in .env.production.example.
# Run once, paste the output into the production .env, and keep a copy somewhere safe.
set -eu
rand() { openssl rand -base64 48 | tr -d '\n/+=' | cut -c1-"$1"; }
echo "POSTGRES_PASSWORD=$(rand 32)"
echo "JWT_SECRET=$(rand 64)"
# Fernet key: 32 random bytes, URL-safe base64.
echo "INTEGRATION_SECRET_KEY=$(openssl rand -base64 32 | tr '+/' '-_')"
echo "PLATFORM_BOOTSTRAP_TOKEN=$(rand 48)"
echo "ASAAS_WEBHOOK_TOKEN=$(rand 48)"
