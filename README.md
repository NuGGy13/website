# website

This is a Flask chat app with a real backend API.

## Setup

1. Install dependencies:

   pip install -r requirements.txt

2. (Optional) Set a Hugging Face API token if you want the chatbot to use an open-source model:

   set HUGGINGFACE_API_TOKEN=your_token_here

3. Run the app:

   python app.py

4. Open `http://127.0.0.1:5000` in your browser.

If no Hugging Face API token is provided, the app will still run using a fallback response provider.
