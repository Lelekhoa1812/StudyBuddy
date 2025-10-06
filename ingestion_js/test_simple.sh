#!/bin/bash

set -euo pipefail

echo "🚀 Testing Ingestion JS API - Simple Test"
echo "=========================================="

# Configuration
BACKEND_URL="https://study-buddy-ingestion1.vercel.app/api"
USER_ID="44e65346-8eaa-4f95-b17a-f6219953e7a8"
PROJECT_ID="496e2fad-ec7e-4562-b06a-ea2491f2460"

# Test file
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FILE1="$SCRIPT_DIR/../exefiles/Lecture5_ML.pdf"

echo "📋 Configuration:"
echo "   Backend URL: $BACKEND_URL"
echo "   User ID: $USER_ID"
echo "   Project ID: $PROJECT_ID"
echo "   File: $FILE1"
echo ""

# Validate file
if [ ! -f "$FILE1" ]; then echo "❌ Missing file: $FILE1"; exit 26; fi

echo "🏥 Step 1: Health Check"
echo "------------------------"
curl -sS -X GET "$BACKEND_URL/health" -H "Accept: application/json" | jq '.' || echo "Health check failed"
echo ""

echo "📁 Step 2: Upload File"
echo "----------------------"
UPLOAD_RESPONSE=$(curl -sS -X POST "$BACKEND_URL/upload" \
  -F "user_id=$USER_ID" \
  -F "project_id=$PROJECT_ID" \
  -F "files=@$FILE1" \
  -w "\nHTTP_STATUS:%{http_code}")

HTTP_STATUS=$(echo "$UPLOAD_RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
RESPONSE_BODY=$(echo "$UPLOAD_RESPONSE" | grep -v "HTTP_STATUS:")

echo "HTTP Status: $HTTP_STATUS"
echo "Response:"
echo "$RESPONSE_BODY" | jq '.' || echo "$RESPONSE_BODY"

if [ "$HTTP_STATUS" != "200" ]; then
  echo "❌ Upload failed with status $HTTP_STATUS"
  exit 1
fi

JOB_ID=$(echo "$RESPONSE_BODY" | jq -r '.job_id // empty')
if [ -z "$JOB_ID" ]; then
  echo "❌ No job_id in response"
  exit 1
fi

echo ""
echo "✅ Upload initiated successfully!"
echo "   Job ID: $JOB_ID"
echo ""

echo "📊 Step 3: Check Status"
echo "-----------------------"
curl -sS -X GET "$BACKEND_URL/upload/status?job_id=$JOB_ID" -H "Accept: application/json" | jq '.' || echo "Status check failed"
echo ""

echo "📋 Step 4: List Files"
echo "---------------------"
curl -sS -X GET "$BACKEND_URL/files?user_id=$USER_ID&project_id=$PROJECT_ID" -H "Accept: application/json" | jq '.' || echo "List files failed"
echo ""

echo "🎉 Simple test completed!"
echo "========================"