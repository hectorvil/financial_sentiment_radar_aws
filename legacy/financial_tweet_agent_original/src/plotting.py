import pandas as pd
import plotly.express as px

def build_sentiment_bar(pivot_df: pd.DataFrame, metric: str):
    """
    Gráfico de barras coloreado: verde = positivo, rojo = negativo.
    """
    limit = min(30, len(pivot_df))
    fig = px.bar(
        pivot_df.sort_values(metric, ascending=False).head(limit),
        x="tickers",
        y=metric,
        color=metric,
        text=metric,
        height=450,
        template="plotly_dark",
        color_continuous_scale="RdYlGn",
    )
    fig.update_layout(
        xaxis_title="Ticker",
        yaxis_title=metric.replace("_", " ").title(),
        xaxis_tickangle=-45,
        coloraxis_showscale=False,
    )
    return fig
