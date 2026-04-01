# Scheduler Plugin

**File:** `aifred/plugins/tools/scheduler_tool.py`

Scheduled tasks and cron jobs that AIfred executes automatically at defined times.

## Tools

| Tool | Description | Tier |
|------|------------|------|
| `scheduler_create` | Create new scheduled job | WRITE_DATA |
| `scheduler_list` | List all scheduled jobs | READONLY |
| `scheduler_delete` | Delete scheduled job | WRITE_SYSTEM |

## Features

- **Cron syntax:** Standard cron expressions for flexible scheduling
- **Isolated sessions:** Each job runs in its own session
- **Webhook API:** Jobs can also be triggered externally via HTTP
- **Auto-restart:** Jobs survive service restarts
