# 📊 Financial-Tweet Agent

Un agente Streamlit interactivo que analiza y clasifica tweets financieros por **tema** y **sentimiento**, permite consultas históricas y en vivo, y visualiza el comportamiento del mercado en un dashboard simple.

---

## ¿Qué hace?

- **Etiquetado automático** de tweets financieros mediante FinBert (sentimiento: `positive`, `neutral`, `negative`. Y también etiqueta por tema en 21 categorías como: `Politics`, `IPO`, `Federal Reserve`, `Gold`, etc.)
- **Chat RAG histórico**: puedes preguntar cosas como *"¿Qué se dice sobre NVIDIA?"*
- **Consulta en vivo**: busca en Twitter (X) y te resume lo más reciente
- **Dashboard visual**: muestra sentimiento por ticker (ej. `AAPL`, `TSLA`, `AMZN`, `MSFT`)

---


## 🔄 Flujo de extremo a extremo

| Etapa | Qué ocurre | Detalles técnicos |
|-------|------------|-------------------|
| **1. Upload / Live fetch** | Ingesta de tweets en bruto (archivo **.parquet** histórico o stream desde la **Twitter API**). | — |
| **2. Data pipeline** | Limpieza → etiquetado → embeddings. | **`clean()`** elimina URLs, menciones y emojis. <br> **FinBERT** (`ProsusAI/finbert`, 110 M parámetros) asigna **positive / neutral / negative**. <br> **Topic classifier** (SVM + MPNet) mapea 20 temas fijos — Dividend, Fed, M&A… <br> **Mini-LM** (`all-MiniLM-L6-v2`) produce un vector por tweet; se salta si la columna `embedding` ya existe. |
| **3. ChromaDB** | Persistencia y búsqueda vectorial. | Almacena `doc_id`, texto y embedding en un índice **HNSW** (*cosine*); responde k-NN en **< 20 ms**. |
| **4. RAG (Retrieval-Augmented Generation)** | Contexto + LLM. | 1) La pregunta se embebe con Mini-LM.<br>2) Chroma devuelve los 30 tweets más cercanos.<br>3) Se arma el prompt:<br><code>: ¿Qué se dice de NVIDIA?</code><br>4) GPT-4o-mini responde usando <i>solo</i> ese contexto. |
| **5. Dashboard** | Métricas de sentimiento. | `agent.pivot()` agrupa por **ticker** y **sentiment**, calcula `pos_ratio / neg_ratio`; **Plotly** renderiza el ranking interactivo. |



---

## Cómo ponerlo en marcha

### A. Ejecutar con notebook (recomendado para pruebas rápidas)

1. Abre `run_agent.ipynb` en Colab, JupyterLab o VS Code.
2. Ejecuta **todas las celdas**:
   - Instala dependencias (solo la primera vez).
   - Pregunta por tus `OPENAI_API_KEY` y `TWITTER_BEARER` (puedes dejarlas vacías).
   - Lanza el dashboard y muestra la URL pública de ngrok.
3. Sube tu `.parquet` desde la interfaz y listo.

> *No necesitas tocar la terminal; el notebook lo hace todo.*

---

### B. Ejecutar desde la terminal

```bash
# 1) Clonar y crear entorno
git clone https://github.com/tu_usuario/financial-tweet-agent.git
cd financial-tweet-agent
python -m venv venv && source venv/bin/activate

# 2) Instalar dependencias
pip install -r requirements.txt

# 3) (Opcional) exportar claves o usar .env
export OPENAI_API_KEY="sk-···"
export TWITTER_BEARER="AAAAAAAA…"

# 4) Lanzar Streamlit (localhost:8501)
streamlit run app.py
