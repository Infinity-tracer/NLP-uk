#!/bin/bash
# AWS Deployment Script for NLP-uk Clinical Pipeline
# Run this from the project root directory

set -e

# ============ CONFIGURATION ============
# UPDATE THESE VALUES
export AWS_ACCOUNT_ID="YOUR_ACCOUNT_ID"      # e.g., 123456789012
export AWS_REGION="us-east-1"
export PROJECT_NAME="nlp-uk"

# ============ STEP 1: Create ECR Repositories ============
echo "Creating ECR repositories..."
aws ecr create-repository --repository-name ${PROJECT_NAME}-api --region ${AWS_REGION} 2>/dev/null || echo "API repo exists"
aws ecr create-repository --repository-name ${PROJECT_NAME}-frontend --region ${AWS_REGION} 2>/dev/null || echo "Frontend repo exists"

# ============ STEP 2: Login to ECR ============
echo "Logging into ECR..."
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

# ============ STEP 3: Build and Push Images ============
echo "Building and pushing API image..."
docker build -t ${PROJECT_NAME}-api .
docker tag ${PROJECT_NAME}-api:latest ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${PROJECT_NAME}-api:latest
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${PROJECT_NAME}-api:latest

echo "Building and pushing Frontend image..."
cd frontend
# Use production nginx config
cp nginx.prod.conf nginx.conf
docker build -t ${PROJECT_NAME}-frontend .
docker tag ${PROJECT_NAME}-frontend:latest ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${PROJECT_NAME}-frontend:latest
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${PROJECT_NAME}-frontend:latest
cd ..

echo "============================================"
echo "Images pushed successfully!"
echo "API:      ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${PROJECT_NAME}-api:latest"
echo "Frontend: ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${PROJECT_NAME}-frontend:latest"
echo "============================================"
echo ""
echo "Next steps:"
echo "1. Create ECS cluster and services via AWS Console or CLI"
echo "2. Set up ALB with target groups"
echo "3. Configure service discovery for internal communication"
echo ""
echo "Or use AWS Copilot for simplified deployment:"
echo "  copilot init --app ${PROJECT_NAME}"
