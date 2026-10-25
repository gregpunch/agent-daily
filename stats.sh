#!/bin/sh
# Usage: ./stats.sh [days]  (needs AGENT_DAILY_STATS_KEY; on the box: source ~/.agent_daily_env)
curl -s "https://agent-daily.agentdaily.workers.dev/stats?days=${1:-1}" -H "Authorization: Bearer $AGENT_DAILY_STATS_KEY"
