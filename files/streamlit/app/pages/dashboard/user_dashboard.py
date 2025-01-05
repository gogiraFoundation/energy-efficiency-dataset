import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

# User dashboard


def user_home(data):
    st.title("Energy Efficiency Analysis")
    st.table(data.head())
    
    # Check if data is None or not a pandas DataFrame
    if not isinstance(data, pd.DataFrame):
        st.error("The data is not loaded properly as a DataFrame.")
        return
    
    # Check if the DataFrame is empty
    if data.empty:
        st.warning("The dataset is empty.")
        return

    # Dataset preview
    st.subheader("Dataset Preview")
    st.write(f"Dataset contains {data.shape[0]} rows and {data.shape[1]} columns.")
    st.write(data.head())

    # Feature selection
    st.sidebar.subheader("Select Features")
    target = st.sidebar.selectbox("Select Target Variable", data.columns)
    features = st.sidebar.multiselect("Select Feature Variables", [col for col in data.columns if col != target])

    # Train-test split and modeling
    if st.sidebar.button("Train Model"):
        if target and features:
            X = data[features]
            y = data[target]

            # Split data
            from sklearn.model_selection import train_test_split
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

            # Standardize the data
            st.sidebar.subheader("Scaling Options")
            scale_data = st.sidebar.checkbox("Scale Data", value=False)

            if scale_data:
                from sklearn.preprocessing import StandardScaler
                scaler = StandardScaler()
                X_train = scaler.fit_transform(X_train)
                X_test = scaler.transform(X_test)

            # Train Linear Regression model
            from sklearn.linear_model import LinearRegression
            model = LinearRegression()
            model.fit(X_train, y_train)

            # Predictions
            y_pred = model.predict(X_test)

            # Evaluation Metrics
            from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
            st.subheader("Model Evaluation")
            st.metric("Mean Absolute Error (MAE)", f"{mean_absolute_error(y_test, y_pred):.4f}")
            st.metric("Mean Squared Error (MSE)", f"{mean_squared_error(y_test, y_pred):.4f}")
            st.metric("R-squared (R²)", f"{r2_score(y_test, y_pred):.4f}")

            # Visualization of Predictions
            import matplotlib.pyplot as plt
            import seaborn as sns
            st.subheader("Prediction vs Actual")
            fig, ax = plt.subplots(figsize=(8, 6))
            sns.scatterplot(x=y_test, y=y_pred, ax=ax, color='blue', label="Predictions")
            ax.plot([y_test.min(), y_test.max()], [y_test.min(), y_test.max()], 'k--', lw=2, label="Ideal")
            ax.set_xlabel("Actual")
            ax.set_ylabel("Predicted")
            ax.legend()
            st.pyplot(fig)
        else:
            st.error("Please select both target and feature variables.")


# Main function to control the flow
def user_main(option, data):
    uploaded_data = data
    user_option = option
    user_home(uploaded_data)
