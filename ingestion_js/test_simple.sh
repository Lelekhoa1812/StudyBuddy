#!/bin/bash

set -euo pipefail

echo "🚀 Simple Test for Ingestion JS API"
echo "===================================="

BACKEND_URL="https://study-buddy-ingestion1.vercel.app/api"
USER_ID="44e65346-8eaa-4f95-b17a-f6219953e7a8"
PROJECT_ID="496e2fad-ec7e-4562-b06a-ea2491f2460"

echo "🏥 Step 1: Health Check"
echo "------------------------"
curl -s "$BACKEND_URL/health"
echo ""
echo ""

echo "📁 Step 2: Upload Small File"
echo "-----------------------------"
# Use Tut5.pdf which is smaller (1.2MB)
FILE1="../exefiles/Tut5.pdf"
if [ ! -f "$FILE1" ]; then
  echo "❌ Missing file: $FILE1"
  exit 1
fi

echo "Uploading $(basename "$FILE1")..."
UPLOAD_RESPONSE=$(curl -s -X POST "$BACKEND_URL/upload" \
  -F "user_id=$USER_ID" \
  -F "project_id=$PROJECT_ID" \
  -F "files=@$FILE1")

echo "Upload response: $UPLOAD_RESPONSE"

# Extract job_id using Python
JOB_ID=$(python3 - <<EOF
import json
try:
    data = json.loads('$UPLOAD_RESPONSE')
    print(data.get('job_id', ''))
except:
    print('')
EOF
)

if [ -z "$JOB_ID" ]; then
  echo "❌ No job_id in response"; exit 1
fi

echo "Job ID: $JOB_ID"
echo ""

echo "📊 Step 3: Check Job Status"
echo "----------------------------"
for i in {1..6}; do
  echo "Check $i/6..."
  STATUS_RESPONSE=$(curl -s "$BACKEND_URL/upload/status?job_id=$JOB_ID")
  echo "Status: $STATUS_RESPONSE"
  
  if echo "$STATUS_RESPONSE" | grep -q '"status":"completed"'; then
    echo "✅ Completed!"; break
  elif echo "$STATUS_RESPONSE" | grep -q '"status":"processing"'; then
    echo "⏳ Processing..."; sleep 10
  else
    echo "❌ Error or unknown status"; break
  fi
  echo ""
done

echo ""
echo "📋 Step 4: List Files"
echo "---------------------"
curl -s "$BACKEND_URL/files?user_id=$USER_ID&project_id=$PROJECT_ID"
echo ""
echo ""

echo "🔍 Step 5: Get Chunks"
echo "---------------------"
curl -s "$BACKEND_URL/files/chunks?user_id=$USER_ID&project_id=$PROJECT_ID&filename=Tut5.pdf&limit=3"
echo ""

echo ""
echo "🎉 Test completed!"