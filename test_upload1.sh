#!/bin/bash

set -euo pipefail

echo "🚀 Testing Ingestion Pipeline Upload"
echo "======================================"

# Configuration
BACKEND_URL="https://binkhoale1812-studdybuddy-ingestion1.hf.space"
USER_ID="44e65346-8eaa-4f95-b17a-f6219953e7a8"
PROJECT_ID="496e2fad-ec7e-4562-b06a-ea2491f2460"

# Test files
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FILE1="$SCRIPT_DIR/../exefiles/Lecture5_ML.pdf"
FILE2="$SCRIPT_DIR/../exefiles/Lecture6_ANN_DL.pdf"


# Debug toggles
DEBUG=${DEBUG:-0}
TRACE=${TRACE:-0}

echo "📋 Configuration:"
echo "   Backend URL: $BACKEND_URL"
echo "   User ID: $USER_ID"
echo "   Project ID: $PROJECT_ID"
echo "   Files: $FILE1, $FILE2"
echo ""

# Validate files and resolve absolute paths
if [ ! -f "$FILE1" ]; then
  echo "❌ Missing file: $FILE1"; exit 26
fi
if [ ! -f "$FILE2" ]; then
  echo "❌ Missing file: $FILE2"; exit 26
fi
FILE1_DIR="$(cd "$(dirname "$FILE1")" && pwd)"; FILE1_BASENAME="$(basename "$FILE1")"; FILE1="$FILE1_DIR/$FILE1_BASENAME"
FILE2_DIR="$(cd "$(dirname "$FILE2")" && pwd)"; FILE2_BASENAME="$(basename "$FILE2")"; FILE2="$FILE2_DIR/$FILE2_BASENAME"

curl_base() {
  local method="$1"; shift
  local url="$1"; shift
  local extra=("$@")
  local common=(
    -L --http1.1 --fail-with-body -sS
    --connect-timeout 60
    --retry 5 --retry-delay 4 --retry-connrefused
  )
  if [ "$DEBUG" = "1" ]; then
    common+=( -v )
  fi
  if [ "$TRACE" = "1" ]; then
    common+=( --trace-time --trace-ascii - )
  fi
  curl -X "$method" "$url" "${common[@]}" "${extra[@]}"
}

json_with_status() {
  local method="$1"; shift
  local url="$1"; shift
  local extra=("$@")
  curl_base "$method" "$url" "${extra[@]}" \
    -w "\nHTTP Status: %{http_code}\n"
}

# Step 0: Preflight (for browser parity)
echo "🛰️  Step 0: OPTIONS /upload (preflight parity)"
echo "---------------------------------------------"
json_with_status OPTIONS "$BACKEND_URL/upload" -H "Origin: https://example.com" -H "Access-Control-Request-Method: POST" || true
echo ""; echo ""

# Step 1: Health Check
echo "🏥 Step 1: Health Check"
echo "------------------------"
json_with_status GET "$BACKEND_URL/health" -H "Accept: application/json" || true
echo ""; echo ""

# Step 2: Upload Files
echo "📁 Step 2: Upload Files (sequential)"
echo "------------------------------------"
echo "Uploading $(basename "$FILE1")..."

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

# Extract job_id (prefer jq)
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

if [ -z "${JOB_ID:-}" ]; then
  echo "❌ Failed to extract job_id from upload response"; exit 1
fi

echo ""
echo "✅ Upload 1 initiated successfully!"
echo "   Job ID: $JOB_ID"
echo ""

# Step 3: Monitor Upload Progress
echo "📊 Step 3: Monitor Upload Progress"
echo "----------------------------------"

for i in {1..48}; do
  echo "Checking progress (attempt $i/12)..."
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

# Now upload second file after first completes
echo "📁 Step 3: Upload second file"
echo "------------------------------"
echo "Uploading $(basename "$FILE2")..."

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

# Extract job_id2
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

echo "📊 Step 4: Monitor Upload 2 Progress"
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

# Step 5: List Uploaded Files
echo "📋 Step 4: List Uploaded Files"
echo "-------------------------------"
json_with_status GET "$BACKEND_URL/files?user_id=$USER_ID&project_id=$PROJECT_ID" -H "Accept: application/json" | sed 's/^/  /'
echo ""; echo ""

# Step 5: Get File Chunks (for Lecture7_GA_EC.pdf)
echo "🔍 Step 5: Get File Chunks for Lecture7_GA_EC.pdf"
echo "----------------------------------------------"
json_with_status GET "$BACKEND_URL/files/chunks?user_id=$USER_ID&project_id=$PROJECT_ID&filename=Lecture7_GA_EC.pdf&limit=5" -H "Accept: application/json" | sed 's/^/  /'
echo ""; echo ""

# Step 6: Get File Chunks (for Tut7.pdf)
echo "🔍 Step 6: Get File Chunks for Tut7.pdf"
echo "------------------------------------------------"
json_with_status GET "$BACKEND_URL/files/chunks?user_id=$USER_ID&project_id=$PROJECT_ID&filename=Tut7.pdf&limit=5" -H "Accept: application/json" | sed 's/^/  /'

echo ""
echo "🎉 Test completed!"
echo "=================="