#!/bin/bash

# Define variables
APP_DIR="files/"  # Replace with the path to your app directory
MAIN_APP_FILE="streamlit/app/pages/homepage.py"
VENV_DIR="$APP_DIR/venv"  # Virtual environment directory
PORT=8501
ADDRESS="0.0.0.0"  # Allow external access

# Function to display messages
function echo_message {
    echo "==================================================="
    echo "$1"
    echo "==================================================="
}

# Navigate to the app directory
if [ -d "$APP_DIR" ]; then
    cd "$APP_DIR" || exit 1
    echo_message "Navigated to app directory: $APP_DIR"
else
    echo_message "Error: App directory not found at $APP_DIR!"
    exit 1
fi

# Create a virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo_message "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    if [ $? -ne 0 ]; then
        echo_message "Error: Failed to create virtual environment!"
        exit 1
    fi
fi

# Activate the virtual environment
echo_message "Activating virtual environment..."
source "$VENV_DIR/bin/activate"
if [ $? -ne 0 ]; then
    echo_message "Error: Failed to activate virtual environment!"
    exit 1
fi

# Verify Python and pip in the virtual environment
echo_message "Verifying Python and pip in the virtual environment..."
python --version || { echo_message "Error: Python not found in virtual environment!"; exit 1; }
pip --version || { echo_message "Error: pip not found in virtual environment!"; exit 1; }

# Install dependencies (if requirements.txt exists)
if [ -f "requirements.txt" ]; then
    echo_message "Installing dependencies..."
    pip install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo_message "Error: Failed to install dependencies!"
        deactivate
        exit 1
    fi
else
    echo_message "Warning: requirements.txt not found. Skipping dependency installation."
fi

# Check if Streamlit is installed
if ! command -v streamlit &>/dev/null; then
    echo_message "Streamlit is not installed. Installing Streamlit..."
    pip install streamlit
    if [ $? -ne 0 ]; then
        echo_message "Error: Failed to install Streamlit!"
        deactivate
        exit 1
    fi
fi

# Run the Streamlit app
echo_message "Launching Streamlit app on $ADDRESS:$PORT..."
streamlit run "$MAIN_APP_FILE" --server.address "$ADDRESS" --server.port "$PORT"
if [ $? -ne 0 ]; then
    echo_message "Error: Failed to launch Streamlit app!"
    deactivate
    exit 1
fi

# Deactivate the virtual environment after exiting Streamlit
echo_message "Deactivating virtual environment..."
deactivate

echo_message "Deployment complete!"