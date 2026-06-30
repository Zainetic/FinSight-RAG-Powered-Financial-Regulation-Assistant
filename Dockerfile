FROM python:3.13-slim

WORKDIR /app

# Copying the requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copying the rest of the application code
COPY . .

# Exposing Streamlit's default port
EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0"]