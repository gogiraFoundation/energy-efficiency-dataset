#!/bin/bash

# Define variables
APP_DIR="files/"  # Replace with the path to your app directory
MAIN_APP_FILE="streamlit/app/pages/homepage.py"  # Replace with your main Streamlit app file
VENV_DIR="$APP_DIR/venv"  # Virtual environment directory

# Function to display messages
function echo_message {
    echo "==================================================="
    echo "$1"
    echo "==================================================="
}

#  Navigate to the app directory
cd "$APP_DIR" || { echo "App directory not found!"; exit 1; }
echo_message "Navigated to app directory: $APP_DIR"

# Create a virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo_message "Creating virtual environment..."
    python3 -m venv "$VENV_DIR" || { echo "Failed to create virtual environment!"; exit 1; }
fi

# Activate the virtual environment
echo_message "Activating virtual environment..."
source "$VENV_DIR/bin/activate" || { echo "Failed to activate virtual environment!"; exit 1; }

# Install dependencies
echo_message "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt || { echo "Failed to install dependencies!"; exit 1; }

# Run the Streamlit app
echo_message "Launching Streamlit app..."
streamlit run "$MAIN_APP_FILE" || { echo "Failed to launch Streamlit app!"; exit 1; }

# Deactivate the virtual environment
echo_message "Deactivating virtual environment..."
deactivate

echo_message "Deployment complete!"
