#!/bin/bash

# Load environment variables from .env
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | xargs)
else
    echo ".env file not found. Please create one with your EMAIL variable."
    exit 1
fi

# Configuration
APP_URL="http://localhost:8501"    # URL of the Streamlit app
THRESHOLD=5                        # Number of failures before sending alert
CHECK_INTERVAL=30                  # Interval between checks in seconds
LOG_DIR="log"                      # Directory to store logs
LOG_FILE="$LOG_DIR/streamlit_health.log"  # Log file name
ALERT_EMAIL="$EMAIL"               # Alert email from the .env file

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Initialize failure counter
failure_count=0

# Function to send notification
send_notification() {
    echo "Streamlit app is down! Consecutive failures reached $THRESHOLD." | mail -s "Streamlit App Health Alert" "$ALERT_EMAIL"
    echo "$(date) - Notification sent to $ALERT_EMAIL" >> "$LOG_FILE"
}

# Monitoring loop
while true; do
    # Check app health
    response=$(curl -s -o /dev/null -w "%{http_code}" "$APP_URL")
    
    if [ "$response" -eq 200 ]; then
        # App is healthy
        echo "$(date) - App is healthy (HTTP $response)" >> "$LOG_FILE"
        failure_count=0  # Reset failure counter
    else
        # App is unhealthy
        echo "$(date) - App is down (HTTP $response)" >> "$LOG_FILE"
        ((failure_count++))
        
        # Send notification if failure threshold is reached
        if [ "$failure_count" -ge "$THRESHOLD" ]; then
            send_notification
            failure_count=0  # Reset failure counter after notification
        fi
    fi

    # Wait for the next check
    sleep "$CHECK_INTERVAL"
done