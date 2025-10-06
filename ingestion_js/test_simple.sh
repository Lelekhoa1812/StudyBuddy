#!/bin/bash

set -euo pipefail

echo "🚀 Testing Ingestion JS API - Simple Test"
echo "=========================================="

# Configuration
BACKEND_URL="https://study-buddy-ingestion1.vercel.app/api"
USER_ID="44e65346-8eaa-4f95-b17a-f6219953e7a8"
PROJECT_ID="496e2fad-ec7e-4562-b06a-ea2491f2460"

# Test files - use smaller files
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FILE1="$SCRIPT_DIR/../exefiles/Tut5.pdf"  # Smaller file

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
curl -sS "$BACKEND_URL/health"
echo ""
echo ""

echo "📁 Step 2: Upload File"
echo "----------------------"
UPLOAD_RESPONSE=$(curl -sS -X POST "$BACKEND_URL/upload" \
  -F "user_id=$USER_ID" \
  -F "project_id=$PROJECT_ID" \
  -F "files=@$FILE1")

echo "Upload response:"
echo "$UPLOAD_RESPONSE"
echo ""

# Extract job_id using grep and sed
JOB_ID=$(echo "$UPLOAD_RESPONSE" | grep -o '"job_id":"[^"]*"' | sed 's/"job_id":"\([^"]*\)"/\1/')

if [ -z "$JOB_ID" ]; then
  echo "❌ Failed to extract job_id"
  exit 1
fi

echo "✅ Upload initiated! Job ID: $JOB_ID"
echo ""

echo "📊 Step 3: Monitor Progress"
echo "---------------------------"
for i in {1..10}; do
  echo "Check $i/10..."
  STATUS_RESPONSE=$(curl -sS "$BACKEND_URL/upload/status?job_id=$JOB_ID")
  echo "Status: $STATUS_RESPONSE"
  
  if echo "$STATUS_RESPONSE" | grep -q '"status":"completed"'; then
    echo "✅ Upload completed!"
    break
  elif echo "$STATUS_RESPONSE" | grep -q '"status":"failed"'; then
    echo "❌ Upload failed!"
    break
  fi
  
  sleep 100
done

echo ""
echo "🔍 Step 4: Debug Job"
echo "--------------------"
curl -sS "$BACKEND_URL/debug?job_id=$JOB_ID"
echo ""
echo ""

echo "📋 Step 5: List Files"
echo "---------------------"
curl -sS "$BACKEND_URL/files?user_id=$USER_ID&project_id=$PROJECT_ID"
echo ""
echo ""

echo "🎉 Test completed!"