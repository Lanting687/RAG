#!/bin/bash
# Quick access to EC2 application logs.
#
# Usage:
#   ./ec2-logs.sh                 # last 50 lines, all services
#   ./ec2-logs.sh backend         # last 50 lines, backend only
#   ./ec2-logs.sh backend -f      # follow backend logs live
#   ./ec2-logs.sh -f              # follow all services live

KEY_PATH="$(dirname "$0")/RAG_KEY_PAIR.pem"
EC2_HOST="ubuntu@16.171.150.168"

SERVICE=""
FOLLOW_FLAG=""

for arg in "$@"; do
  if [ "$arg" = "-f" ] || [ "$arg" = "--follow" ]; then
    FOLLOW_FLAG="-f"
  else
    SERVICE="$arg"
  fi
done

if [ -n "$FOLLOW_FLAG" ]; then
  ssh -i "$KEY_PATH" "$EC2_HOST" "cd ~/RAG && docker compose logs -f $SERVICE"
else
  ssh -i "$KEY_PATH" "$EC2_HOST" "cd ~/RAG && docker compose logs --tail=50 $SERVICE"
fi
