#!/bin/bash

set -euo pipefail

echo "🚀 Testing Ingestion JS API on Vercel"
echo "======================================"

# Configuration
BACKEND_URL="https://study-buddy-ingestion1.vercel.app/api"
USER_ID="44e65346-8eaa-4f95-b17a-f6219953e7a8"
PROJECT_ID="496e2fad-ec7e-4562-b06a-ea2491f2460"

# Test files
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FILE1="$SCRIPT_DIR/../exefiles/Lecture5_ML.pdf"
FILE2="$SCRIPT_DIR/../exefiles/Lecture6_ANN_DL.pdf"

DEBUG=${DEBUG:-0}
TRACE=${TRACE:-0}

echo "📋 Configuration:"
echo "   Backend URL: $BACKEND_URL"
echo "   User ID: $USER_ID"
echo "   Project ID: $PROJECT_ID"
echo "   Files: $FILE1, $FILE2"
echo ""

# Validate files
if [ ! -f "$FILE1" ]; then echo "❌ Missing file: $FILE1"; exit 26; fi
if [ ! -f "$FILE2" ]; then echo "❌ Missing file: $FILE2"; exit 26; fi

curl_base() {
  local method="$1"; shift
  local url="$1"; shift
  local extra=("$@")
  local common=(
    -L --http1.1 --fail-with-body -sS
    --connect-timeout 60
    --retry 5 --retry-delay 4 --retry-connrefused
  )
  if [ "$DEBUG" = "1" ]; then common+=( -v ); fi
  if [ "$TRACE" = "1" ]; then common+=( --trace-time --trace-ascii - ); fi
  curl -X "$method" "$url" "${common[@]}" "${extra[@]}"
}

json_with_status() {
  local method="$1"; shift
  local url="$1"; shift
  local extra=("$@")
  curl_base "$method" "$url" "${extra[@]}" -w "\nHTTP Status: %{http_code}\n"
}

echo "🛰️  Step 0: OPTIONS /api/upload (preflight parity)"
echo "---------------------------------------------"
json_with_status OPTIONS "$BACKEND_URL/upload" -H "Origin: https://example.com" -H "Access-Control-Request-Method: POST" || true

echo ""
echo "🏥 Step 1: Health Check"
echo "------------------------"
json_with_status GET "$BACKEND_URL/health" -H "Accept: application/json" || true

echo ""
echo "📁 Step 2: Upload Files (first file)"
echo "------------------------------------"
UPLOAD_HEADERS=$(mktemp)
UPLOAD_BODY=$(mktemp)

set +e
HTTP_CODE=$(curl -L --http1.1 --fail-with-body -sS \
  --connect-timeout 60 --retry 3 --retry-delay 4 --retry-connrefused \
  -H "Expect:" \
  -X POST "$BACKEND_URL/upload" \
  -F "user_id=$USER_ID" \
  -F "project_id=$PROJECT_ID" \
  -F "files=@$FILE1" \
  -D "$UPLOAD_HEADERS" -o "$UPLOAD_BODY" \
  -w "%{http_code}")
RET=$?
set -e

echo "HTTP Status: $HTTP_CODE"
echo "--- Response Headers ---"; sed -e 's/\r$//' "$UPLOAD_HEADERS" | sed 's/^/  /'
echo "--- Response Body ---"; sed 's/^/  /' "$UPLOAD_BODY"

if [ "$RET" -ne 0 ] || [ "$HTTP_CODE" = "000" ]; then
  echo "❌ Upload failed (curl exit=$RET, http=$HTTP_CODE)"; exit 1
fi

if command -v jq >/dev/null 2>&1; then
  JOB_ID=$(jq -r '.job_id // empty' < "$UPLOAD_BODY")
else
  JOB_ID=$(python3 - <<'PY'
import sys, json
try:
  data=json.load(sys.stdin)
  print(data.get('job_id',''))
except Exception:
  print('')
PY
  < "$UPLOAD_BODY")
fi

echo "Extracted JOB_ID: '$JOB_ID'"

if [ -z "${JOB_ID:-}" ]; then
  echo "❌ Failed to extract job_id from upload response"; exit 1
fi

echo ""
echo "✅ Upload 1 initiated successfully!"
echo "   Job ID: $JOB_ID"
echo ""

echo "📊 Step 3: Monitor Upload Progress"
echo "----------------------------------"
for i in {1..48}; do
  echo "Checking progress (attempt $i/48)..."
  json_with_status GET "$BACKEND_URL/upload/status?job_id=$JOB_ID" -H "Accept: application/json" | sed 's/^/  /'
  STATUS_LINE=$(json_with_status GET "$BACKEND_URL/upload/status?job_id=$JOB_ID" -H "Accept: application/json" | tail -n +1)
  if echo "$STATUS_LINE" | grep -q '"status":"completed"'; then
    echo "✅ Upload completed successfully!"; break
  elif echo "$STATUS_LINE" | grep -q '"status":"processing"'; then
    echo "⏳ Still processing... waiting 20 seconds"; sleep 20
  else
    echo "❌ Upload failed or unknown status"; break
  fi
  echo ""
done

echo ""
echo "📁 Step 4: Upload second file"
echo "------------------------------"
UPLOAD_HEADERS2=$(mktemp)
UPLOAD_BODY2=$(mktemp)

set +e
HTTP_CODE2=$(curl -L --http1.1 --fail-with-body -sS \
  --connect-timeout 60 --retry 3 --retry-delay 4 --retry-connrefused \
  -H "Expect:" \
  -X POST "$BACKEND_URL/upload" \
  -F "user_id=$USER_ID" \
  -F "project_id=$PROJECT_ID" \
  -F "files=@$FILE2" \
  -D "$UPLOAD_HEADERS2" -o "$UPLOAD_BODY2" \
  -w "%{http_code}")
RET2=$?
set -e

echo "HTTP Status: $HTTP_CODE2"
echo "--- Response Headers ---"; sed -e 's/\r$//' "$UPLOAD_HEADERS2" | sed 's/^/  /'
echo "--- Response Body ---"; sed 's/^/  /' "$UPLOAD_BODY2"

if [ "$RET2" -ne 0 ] || [ "$HTTP_CODE2" = "000" ]; then
  echo "❌ Upload 2 failed (curl exit=$RET2, http=$HTTP_CODE2)"; exit 1
fi

if command -v jq >/dev/null 2>&1; then
  JOB_ID2=$(jq -r '.job_id // empty' < "$UPLOAD_BODY2")
else
  JOB_ID2=$(python3 - <<'PY'
import sys, json
try:
  data=json.load(sys.stdin)
  print(data.get('job_id',''))
except Exception:
  print('')
PY
  < "$UPLOAD_BODY2")
fi

if [ -z "${JOB_ID2:-}" ]; then
  echo "❌ Failed to extract job_id from second upload response"; exit 1
fi

echo ""
echo "✅ Upload 2 initiated successfully!"
echo "   Job ID: $JOB_ID2"
echo ""

echo "📊 Step 5: Monitor Upload 2 Progress"
echo "-------------------------------------"
for i in {1..48}; do
  echo "Checking progress (attempt $i/48)..."
  json_with_status GET "$BACKEND_URL/upload/status?job_id=$JOB_ID2" -H "Accept: application/json" | sed 's/^/  /'
  STATUS_LINE=$(json_with_status GET "$BACKEND_URL/upload/status?job_id=$JOB_ID2" -H "Accept: application/json" | tail -n +1)
  if echo "$STATUS_LINE" | grep -q '"status":"completed"'; then
    echo "✅ Upload 2 completed successfully!"; break
  elif echo "$STATUS_LINE" | grep -q '"status":"processing"'; then
    echo "⏳ Still processing... waiting 20 seconds"; sleep 20
  else
    echo "❌ Upload 2 failed or unknown status"; break
  fi
  echo ""
done

echo ""
echo "📋 Step 6: List Uploaded Files"
echo "-------------------------------"
json_with_status GET "$BACKEND_URL/files?user_id=$USER_ID&project_id=$PROJECT_ID" -H "Accept: application/json" | sed 's/^/  /'

echo ""
echo "🔍 Step 7: Get File Chunks for Lecture5_ML.pdf"
echo "-----------------------------------------------"
json_with_status GET "$BACKEND_URL/files/chunks?user_id=$USER_ID&project_id=$PROJECT_ID&filename=Lecture5_ML.pdf&limit=5" -H "Accept: application/json" | sed 's/^/  /'

echo ""
echo "🎉 Test completed!"
echo "=================="
