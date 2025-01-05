import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler



def data_input():
    chart_title = st.text_input('Chart Title: ')  # Collect chart title as a string
    target_columns = []  # Initialize an empty list to store column names
    count = int(st.number_input("Number of Input Field"))  # Collect the number of input fields
    
    # Iterate for the specified number of input fields
    for x in range(count):  
        target_axis_name = st.text_input(f'Enter Name for Field {x + 1}: ')  # Collect each column name
        target_columns.append(target_axis_name)  # Append it to the list
    
    return target_columns, chart_title  # Return the collected values
    pass


def feature_importance_analysis():
    """Analyzes and visualizes feature importance."""
    st.title("Feature Importance")
    st.write("This is the feature importance based on the linear regression model.")
    
    # Sample feature importance data
    feature_importance = pd.DataFrame({
        'Feature': ['Wall Area', 'Overall Height', 'Compactness_Surface_Area'],
        'Coefficient': [0.0349, 5.5639, 1.0103]
    })
    
    # Display chart and data in tabs
    chart_tabs(feature_importance)


def chart_tabs(data):
    """Creates tabs to display charts and raw data."""
    tab1, tab2 = st.tabs(["📈 Chart", "🗃 Data"])
    
    with tab1:
        st.subheader('Feature Importance Chart')
        plt.figure(figsize=(10, 6))
        st.bar_chart(data.set_index('Feature')['Coefficient'])
    

    with tab2:
        st.subheader("Feature Importance Chart")
        # Display metrics for each feature
        for index, row in data.iterrows():
            col1, col2 = st.columns(2)
            col1.metric(label="Feature", value=row['Feature'])
            col2.metric(label="Coefficient", value=f"{row['Coefficient']:.4f}")



def model_evaluation_analysis():
    st.title("Model Evaluation")
    st.write("This section shows model evaluation metrics like MAE, MSE, and R².")
    
    # Example metrics
    metrics = {
        'Metric': ['MAE', 'MSE', 'R²'],
        'Heating Load': [2.9587, 15.6478, 0.8499],
        'Cooling Load': [2.7554, 13.4406, 0.8549]
    }
    
    metrics_df = pd.DataFrame(metrics)
    # Visualization
    st.subheader("Model Evaluation Metrics Chart")
    metrics_df_melted = metrics_df.melt(id_vars='Metric', var_name='Model', value_name='Value')

    # Create two columns for the metrics
    a, b = st.columns(2)
    with a:
        st.metric(label="Heating Load MAE", value=f"{metrics['Heating Load'][0]:.4f}")
        st.metric(label="Cooling Load MAE", value=f"{metrics['Cooling Load'][0]:.4f}")
    with b:
        st.metric(label="Heating Load MSE", value=f"{metrics['Heating Load'][1]:.4f}")
        st.metric(label="Cooling Load MSE", value=f"{metrics['Cooling Load'][1]:.4f}")

    c, d = st.columns(2)
    with c:
        st.metric(label="Heating Load R²", value=f"{metrics['Heating Load'][2]:.4f}")
    with d:
        st.metric(label="Cooling Load R²", value=f"{metrics['Cooling Load'][2]:.4f}")
    
    # Plotting a bar chart for the metrics
    chart_data = metrics_df_melted.pivot(index='Metric', columns='Model', values='Value')
    st.bar_chart(chart_data)




def cross_validation_analysis():
    st.title("Cross-validation Results")
    st.write("This section shows the cross-validation performance of the model.")
    
    # Default cross-validation MSE data
    mse_values = [16.8033, 14.8618]
    cross_val_df = pd.DataFrame({
        'Model': ['Heating Load', 'Cooling Load'],
        'MSE': mse_values
    })
    
    # Display metrics for each model
    st.subheader("MSE Metrics")
    col1, col2 = st.columns(2)
    with col1:
        st.metric(label="Heating Load MSE", value=f"{mse_values[0]:.4f}")
    with col2:
        st.metric(label="Cooling Load MSE", value=f"{mse_values[1]:.4f}")
    
    # Visualization: Cross-validation MSE Chart
    st.subheader("Cross-validation MSE Chart")
    st.bar_chart(cross_val_df.set_index('Model'))  


# Main handler to process different options
def main_handler(option, data):
    # Initialize session state variables if they don't exist
    if 'bar' not in st.session_state:
        st.session_state.bar = 'Initial Value'
    
    st.write(f"Current value of 'bar': {st.session_state.bar}")

    if option == "Feature Importance":
        feature_importance_analysis()
    elif option == "Model Evaluation":
        model_evaluation_analysis()
    elif option == "Cross-validation":
        cross_validation_analysis()



# Example usage
if __name__ == "__main__":
    main_handler(option, data)



