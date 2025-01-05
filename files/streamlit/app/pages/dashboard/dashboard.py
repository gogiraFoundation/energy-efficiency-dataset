import streamlit as st
import pandas as pd
import os

from dashboard.handlers import main_handler
from dashboard.user_dashboard import user_main

def dataload(file_path):
    """Loads dataset from a specified file path."""
    try:
        data = pd.read_csv(file_path)
        st.success("Dataset loaded successfully!")
        return data
    except FileNotFoundError:
        st.error(f"File not found at the path: {file_path}")
        st.write("Current working directory:", os.getcwd())
    except Exception as e:
        st.error(f"An error occurred: {e}")
    return None

def template(data):
    """Displays the first few rows of the dataset."""
    if data is not None:
        st.subheader("Dataset Preview")
        st.table(data.head())
    else:
        st.warning("No data available to display.")

def action_handler(user_action, option, data):
    """Handles actions based on user input."""
    if user_action == "Yes":
        st.success("Great! Let's proceed with the analysis.")
        if data is not None:
            user_main(option, data)
        else:
            st.warning("Please upload a valid dataset or use the default dataset.")
    elif user_action == "No":
        main_handler()

def sidebar(default_file_path):
    """Handles the sidebar UI and dataset loading."""
    st.sidebar.title("Model and Data Analysis")
    st.sidebar.info(
        "This app analyzes energy efficiency data and builds a regression model to predict outcomes."
    )

    # User action selection
    user_action = st.sidebar.selectbox("Would you like to use the app?", ["Yes", "No"])

    # File upload
    uploaded_file = st.sidebar.file_uploader("Upload a CSV file", type=["csv"])
    option = st.sidebar.selectbox(
        "Select an analysis option",
        ["Feature Importance", "Model Evaluation", "Cross-validation"],
        help="Choose the analysis you'd like to perform."
    )

    # Load dataset
    if "data" not in st.session_state:
        if uploaded_file:
            try:
                # Load uploaded file
                uploaded_dataframe = pd.read_csv(uploaded_file)
                st.session_state.data = uploaded_dataframe
                st.success("Uploaded dataset loaded successfully!")
            except Exception as e:
                st.error(f"Error loading uploaded file: {e}")
                st.session_state.data = None
        else:
            st.session_state.data = dataload(default_file_path)
            if st.session_state.data is None:
                st.warning("No dataset loaded.")
            else:
                st.info(f"Loaded default dataset from {default_file_path}")
    else:
        st.info("Dataset already loaded.")

    return user_action, option, st.session_state.data

def dashboard_main():
    """Main function to manage dashboard flow."""
    # Define default dataset path
    base_dir = os.path.abspath(os.path.join(os.getcwd(), "../../../.."))
    default_file_path = os.path.join(base_dir, "files/data", "linear_regression_energy_eff_dataset.csv")

    # Sidebar and data loading
    user_action, option, data = sidebar(default_file_path)

    # Action handler based on user input
    action_handler(user_action, option, data)

if __name__ == '__main__':
    dashboard_main()
