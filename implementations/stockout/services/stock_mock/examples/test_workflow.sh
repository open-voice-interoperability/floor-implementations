#!/bin/bash

# Complete Test Workflow for Open Floor Protocol
# This script tests a complete multi-agent workflow

set -e

BASE_URL="http://localhost:8000/api/v1"
CONV_ID="conv_workflow_$(date +%s)"

echo "=========================================="
echo "Open Floor Protocol - Test Workflow"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}Step 1: Health Check${NC}"
curl -s http://localhost:8000/health | jq .
echo ""

echo -e "${BLUE}Step 2: Agent Registration${NC}"

echo "Registering Agent 1 (Text Generation)..."
curl -s -X POST $BASE_URL/agents/register \
  -H "Content-Type: application/json" \
  -d '{
    "speakerUri": "tag:test.com,2025:agent_text",
    "agent_name": "Text Generation Agent",
    "capabilities": ["text_generation"],
    "serviceUrl": "http://localhost:8001",
    "conversationalName": "TextBot"
  }' | jq -r '.speakerUri // "ERROR"'
echo ""

echo "Registering Agent 2 (Image Generation)..."
curl -s -X POST $BASE_URL/agents/register \
  -H "Content-Type: application/json" \
  -d '{
    "speakerUri": "tag:test.com,2025:agent_image",
    "agent_name": "Image Generation Agent",
    "capabilities": ["image_generation"],
    "serviceUrl": "http://localhost:8002",
    "conversationalName": "ImageBot"
  }' | jq -r '.speakerUri // "ERROR"'
echo ""

echo "Registering Agent 3 (Data Analysis)..."
curl -s -X POST $BASE_URL/agents/register \
  -H "Content-Type: application/json" \
  -d '{
    "speakerUri": "tag:test.com,2025:agent_data",
    "agent_name": "Data Analysis Agent",
    "capabilities": ["data_analysis"],
    "serviceUrl": "http://localhost:8003",
    "conversationalName": "DataBot"
  }' | jq -r '.speakerUri // "ERROR"'
echo ""

echo -e "${BLUE}Step 3: List Registered Agents${NC}"
curl -s $BASE_URL/agents/ | jq '.[] | {speakerUri, agent_name, capabilities}'
echo ""

echo -e "${BLUE}Step 4: Discovery by Capability${NC}"
echo "Searching for agents with capability 'text_generation'..."
curl -s $BASE_URL/agents/capability/text_generation | jq '.[] | {speakerUri, agent_name}'
echo ""

echo -e "${BLUE}Step 5: Floor Control - Floor Request${NC}"
echo "Agent 1 requests floor..."
RESPONSE=$(curl -s -X POST $BASE_URL/floor/request \
  -H "Content-Type: application/json" \
  -d "{
    \"conversation_id\": \"$CONV_ID\",
    \"speakerUri\": \"tag:test.com,2025:agent_text\",
    \"priority\": 5
  }")
echo $RESPONSE | jq .
GRANTED=$(echo $RESPONSE | jq -r '.granted')
echo ""

if [ "$GRANTED" = "true" ]; then
  echo -e "${GREEN}✓ Floor granted to Agent 1${NC}"
else
  echo -e "${YELLOW}⚠ Floor not granted immediately${NC}"
fi
echo ""

echo "Agent 2 requests floor (will be queued)..."
curl -s -X POST $BASE_URL/floor/request \
  -H "Content-Type: application/json" \
  -d "{
    \"conversation_id\": \"$CONV_ID\",
    \"speakerUri\": \"tag:test.com,2025:agent_image\",
    \"priority\": 3
  }" | jq .
echo ""

echo "Agent 3 requests floor (will be queued)..."
curl -s -X POST $BASE_URL/floor/request \
  -H "Content-Type: application/json" \
  -d "{
    \"conversation_id\": \"$CONV_ID\",
    \"speakerUri\": \"tag:test.com,2025:agent_data\",
    \"priority\": 4
  }" | jq .
echo ""

echo -e "${BLUE}Step 6: Check Floor Holder${NC}"
HOLDER=$(curl -s $BASE_URL/floor/holder/$CONV_ID | jq -r '.holder')
echo "Current floor holder: $HOLDER"
echo ""

echo -e "${BLUE}Step 7: Send Utterance${NC}"
echo "Agent 1 sends utterance to Agent 2..."
curl -s -X POST $BASE_URL/envelopes/utterance \
  -H "Content-Type: application/json" \
  -d "{
    \"conversation_id\": \"$CONV_ID\",
    \"sender_speakerUri\": \"tag:test.com,2025:agent_text\",
    \"target_speakerUri\": \"tag:test.com,2025:agent_image\",
    \"text\": \"Can you generate an image of a sunset?\"
  }" | jq '.success'
echo ""

echo -e "${BLUE}Step 8: Release Floor${NC}"
echo "Agent 1 releases floor..."
curl -s -X POST $BASE_URL/floor/release \
  -H "Content-Type: application/json" \
  -d "{
    \"conversation_id\": \"$CONV_ID\",
    \"speakerUri\": \"tag:test.com,2025:agent_text\"
  }" | jq .
echo ""

echo -e "${BLUE}Step 9: Check New Floor Holder${NC}"
NEW_HOLDER=$(curl -s $BASE_URL/floor/holder/$CONV_ID | jq -r '.holder')
echo "New floor holder: $NEW_HOLDER"
echo ""

echo -e "${BLUE}Step 10: Heartbeat Update${NC}"
echo "Agent 1 updates heartbeat..."
curl -s -X POST $BASE_URL/agents/heartbeat \
  -H "Content-Type: application/json" \
  -d '{
    "speakerUri": "tag:test.com,2025:agent_text"
  }' | jq .
echo ""

echo -e "${GREEN}=========================================="
echo "Test Workflow Completed!"
echo "==========================================${NC}"
echo ""
echo "Conversation ID: $CONV_ID"
echo "You can continue testing with this conversation_id"
echo ""
echo "Useful commands:"
echo "  - List agents: curl $BASE_URL/agents/ | jq"
echo "  - Floor holder: curl $BASE_URL/floor/holder/$CONV_ID | jq"
echo "  - Swagger UI: http://localhost:8000/docs"
