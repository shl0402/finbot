# FinChat Prototype

This repository contains the front-end prototype for a financial chatbot application. Currently utilizing a local Mistral model via Ollama, the architecture is designed to be highly modular. This allows for a seamless transition to a custom ontology-based LLM and live quantitative data APIs in future development phases.

## Overview

The application is built with Streamlit and features a custom "Neo-Tech" UI design to provide a professional, data-dense environment suitable for financial analysis. It supports dynamic visual dashboards and a complex, branched chat history management system.

## Key Features

* **Branched Chat History:** Users can edit previous messages and navigate through different conversation branches (e.g., `< 1/2 >`) without losing prior context, managed via a custom tree-based state management system.
* **Dynamic Visual Analysis:** Dedicated screen real estate for quantitative dashboards.
    * *Market Discovery:* Sector heatmaps (treemaps) and algorithmic stock screeners.
    * *Stock Deep Dive:* Candlestick price action charts and AI-driven sentiment gauges.
* **Modular API Integration:** Chat logic and UI rendering are decoupled, making it straightforward to replace the current local Ollama calls with an external trading or LLM API.
* **Professional UI/CSS:** Custom CSS injection overrides default Streamlit styling to create a dark-themed, immersive web app experience.

## Prerequisites

* Python 3.9+
* [Ollama](https://ollama.com/) installed and running locally.
* The `mistral` model pulled in Ollama (`ollama run mistral`).

## Installation

1.  Clone the repository:
    ```bash
    git clone [https://github.com/yourusername/finchat-prototype.git](https://github.com/yourusername/finchat-prototype.git)
    cd finchat-prototype
    ```

2.  Create a virtual environment (recommended):
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

3.  Install the dependencies:
    ```bash
    pip install -r requirements.txt
    ```

## Usage

1.  Ensure the Ollama application is running in the background.
2.  Start the Streamlit application:
    ```bash
    streamlit run app.py
    ```
3.  Open your browser to `http://localhost:8501`.
4.  Use the sidebar to toggle the visual analysis dashboards, and the main chat interface to interact with the model.

## Future Roadmap

* Replace the local Mistral model with the core ontology LLM API.
* Connect the Plotly dashboards to real-time market data endpoints (e.g., Yahoo Finance, Alpaca, or custom scraping scripts).
* Implement user authentication and save chat trees to a database.