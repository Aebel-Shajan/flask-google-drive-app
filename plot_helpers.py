import io
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import base64
import calplot

def create_plot_from_data(file_content, plot_function):
    plt.switch_backend('Agg')
    # Assuming the file is a CSV - adjust as needed
    df = pd.read_csv(io.BytesIO(file_content))
    
    # Example plot - customize based on your data
    plot_function(df)
    # Save plot to a bytes buffer
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', bbox_inches='tight')
    buffer.seek(0)
    
    # Encode plot to base64 for embedding in HTML
    plot_data = base64.b64encode(buffer.getvalue()).decode()
    plt.close()
    
    return plot_data

def plot_strong_data(df: pd.DataFrame):
    df["date"] = df["date"].apply(pd.to_datetime)
    df = (
        df
        .groupby(by=["date", "workout_name"])
        .agg({
            "total_reps": "sum", 
            "workout_duration_minutes": "min", 
            "total_volume": "sum"
        })
    ).reset_index()
    plot_heatmap(df['workout_duration_minutes'].values, df['date'].values, vmax=120)

def plot_heatmap(intensity: np.ndarray, dates: np.ndarray, vmax:int=100):
    events = pd.Series(intensity, index=dates)
    calplot.calplot(events, cmap="Greens", vmax=vmax)
    