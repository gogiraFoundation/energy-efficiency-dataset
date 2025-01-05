import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

# Import the functions from other scripts
from dashboard.dashboard import dashboard_main



def homepage():
    st.title("Energy Efficiency Analysis Dashboard")
    tab1, tab2, tab3 = st.tabs(["Home", "Model", "Notes"])
    
    with tab1:
        st.subheader("Exploratory Data Analysis")
        data = dashboard_main() # template

    with tab2:
        st.header("Model")
        st.image("https://static.streamlit.io/examples/dog.jpg", width=200)
    with tab3:
        st.header("Notes")
        st.image("https://static.streamlit.io/examples/owl.jpg", width=200)
        

# Main function to control the flow
def main():
    # Sidebar handling
    #data = sidebar()
    homepage()
    

# Check if the script is run directly
if __name__ == '__main__':
    main()
