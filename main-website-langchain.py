import os
import logging
import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, jsonify
import google.generativeai as genai  # Import Google's Generative AI library

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
DATA_DIR = 'data'  # Define the data directory
WEBSITE_TEXT_FILE = os.path.join(DATA_DIR, 'midvale_clinic_text.txt')
TARGET_URL = "https://www.midvalecommunityclinic.com/"
MAX_PROMPT_LENGTH = 3000

# Initialize the Flask application
app = Flask(__name__)

# Configure Gemini API
genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))  # Set your environment variable name

# Function to extract text from the website
def extract_text_from_website(url):
    """
    This function fetches the content from a given URL and extracts the text 
    from all paragraph tags on the page.

    Parameters:
        url (str): The URL of the website to extract content from.

    Returns:
        str: The extracted text from all paragraph elements on the page.
    """
    try:
        # Send a GET request to the URL
        logger.info(f"Fetching content from {url}")
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            # Parse the HTML content using BeautifulSoup
            soup = BeautifulSoup(response.content, 'html.parser')
            text = ""

            # Extract text from all paragraph tags
            for paragraph in soup.find_all('p'):
                text += paragraph.get_text(strip=True) + "\n\n"
                
            # Also get text from headings
            for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                text += heading.get_text(strip=True) + "\n\n"
                
            # Get text from list items
            for li in soup.find_all('li'):
                text += "• " + li.get_text(strip=True) + "\n"
                
            logger.info(f"Successfully extracted {len(text)} characters of text")
            return text
        else:
            error_msg = f"Failed to retrieve website content. Status code: {response.status_code}"
            logger.error(error_msg)
            return error_msg
    except requests.RequestException as e:
        error_msg = f"Request error: {e}"
        logger.error(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"Error extracting website content: {e}"
        logger.error(error_msg)
        return error_msg

def get_website_text():
    """
    Get the website text, either from the cached file or by fetching it again.
    
    Returns:
        str: The extracted website text.
    """
    import time  # Import time module

    # Create data directory if it doesn't exist
    os.makedirs(DATA_DIR, exist_ok=True)

    if os.path.exists(WEBSITE_TEXT_FILE):
        try:
            # Check if the file is recent (less than a day old)
            file_age = os.path.getmtime(WEBSITE_TEXT_FILE)
            if (time.time() - file_age) < 86400:  # 24 hours in seconds
                logger.info(f"Loading website text from cache file: {WEBSITE_TEXT_FILE}")
                with open(WEBSITE_TEXT_FILE, 'r', encoding='utf-8') as file:
                    return file.read()
        except Exception as e:
            logger.warning(f"Error reading cache file: {e}")
    
    # If we reach here, either the file doesn't exist or is too old
    extracted_text = extract_text_from_website(TARGET_URL)
    
    # Save the extracted text
    try:
        with open(WEBSITE_TEXT_FILE, 'w', encoding='utf-8') as text_file:
            text_file.write(extracted_text)
        logger.info(f"Website text saved to {WEBSITE_TEXT_FILE}")
    except Exception as e:
        logger.error(f"Error saving website text: {e}")
    
    return extracted_text


def query_gemini(prompt_text, question, language='en'):
    """
    Query the Gemini API with a given prompt and question in the specified language.
    """
    try:
        # Check for common queries that might not be in the website data
        contact_keywords_en = ["hours", "schedule", "when are you open", "opening hours", "closing time", "business hours"]
        contact_keywords_es = ["horario", "horas", "horarios", "cuando abren", "cuando cierran", "horas de atención", "hora de apertura", "hora de cierre"]
        
        # Check if the question is about hours/schedule
        is_hours_question_en = any(keyword in question.lower() for keyword in contact_keywords_en) and language == 'en'
        is_hours_question_es = any(keyword in question.lower() for keyword in contact_keywords_es) and language == 'es'
        
        if is_hours_question_en:
            return "I don't have the exact information about our current hours of operation. For the most up-to-date schedule, please call our main phone number at (555) 123-4567. Our staff will be happy to assist you with information about our operating hours and help you schedule an appointment if needed."
        
        if is_hours_question_es:
            return "No tengo la información exacta sobre nuestro horario actual de atención. Para obtener el horario más actualizado, por favor llame a nuestro número principal (555) 123-4567. Nuestro personal estará encantado de ayudarle con información sobre nuestros horarios de atención y ayudarle a programar una cita si es necesario."
        
        # Limit the prompt length if it's too long
        if len(prompt_text) > MAX_PROMPT_LENGTH:
            prompt_text = prompt_text[:MAX_PROMPT_LENGTH]
            logger.warning(f"Prompt text truncated to {MAX_PROMPT_LENGTH} characters")
        
        # Create the full prompt based on language
        if language == 'es':
            full_prompt = f"""Basado en la siguiente información sobre la Clínica Comunitaria de Midvale, 
            por favor responde la pregunta en español. Si la pregunta no está relacionada con la clínica, responde con,
            "Lo siento, no puedo ayudarte con eso. ¿Tienes alguna pregunta sobre la Clínica Comunitaria de Midvale?"
            
            Si la información solicitada no está en los datos proporcionados, especialmente para preguntas sobre horarios 
            de atención, direcciones exactas o números de teléfono, responde: "Para obtener información actualizada sobre 
            nuestros horarios y servicios, por favor llame a nuestro número principal (555) 123-4567."
            
            Información sobre la clínica:
            {prompt_text}
            
            Pregunta: {question}
            Respuesta en español:"""
        else:
            full_prompt = f"""Based on the following information about Midvale Community Clinic, 
            please answer the question in English. If the question is not related to the clinic, respond with,
            "I'm sorry, I can't help with that. Do you have any questions about Midvale Community Clinic?"
            
            If the requested information is not in the provided data, especially for questions about operating hours, 
            exact directions, or phone numbers, respond with: "For up-to-date information about our hours and services, 
            please call our main number at (555) 123-4567."
            
            Information about the clinic:
            {prompt_text}
            
            Question: {question}
            Answer in English:"""
        
        # Get available models first (for debugging)
        models = genai.list_models()
        logger.info(f"Available models: {[model.name for model in models]}")
        
        # Get the model - try with the full model name including version
        try:
            model = genai.GenerativeModel('gemini-1.5-pro')
        except Exception as model_error:
            logger.error(f"Error with model 'gemini-1.5-pro': {model_error}")
            # Fallback to another model if available
            model = genai.GenerativeModel(models[0].name)
            logger.info(f"Using fallback model: {models[0].name}")
        
        # Generate content
        logger.info(f"Sending question to Gemini in {language}: {question}")
        response = model.generate_content(full_prompt)
        
        logger.info("Received response from Gemini")
        
        # Extract the text from the response
        return response.text
        
    except Exception as e:
        logger.error(f"Error querying Gemini: {e}")
        if language == 'es':
            return f"Lo siento, hubo un error al procesar tu solicitud: {str(e)}"
        else:
            return f"I'm sorry, there was an error processing your request: {str(e)}"


# Route for the homepage
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/chatbot", methods=["POST"])
def chatbot():
    """
    Handle POST requests to /chatbot, process the question, and return the response.

    Returns:
        JSON: A JSON response containing the model's answer.
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"response": "No data received"}), 400
            
        question = data.get("question", "")
        language = data.get("language", "en")  # Default to English if not specified
        
        if not question:
            return jsonify({"response": "No question provided"}), 400
            
        logger.info(f"Received question in {language}: {question}")
        
        # Get the website text
        prompt = get_website_text()
        
        # Query Gemini with language preference
        response = query_gemini(prompt, question, language)
        
        logger.info(f"Returning response for question in {language}: {question}")
        
        # Return the response as JSON
        return jsonify({"response": response})
        
    except Exception as e:
        logger.error(f"Error in chatbot endpoint: {e}")
        if data and data.get("language") == "es":
            return jsonify({"response": f"Ocurrió un error: {str(e)}"}), 500
        else:
            return jsonify({"response": f"An error occurred: {str(e)}"}), 500


# Run the Flask app
if __name__ == "__main__":
    # Create data directory if it doesn't exist
    os.makedirs(DATA_DIR, exist_ok=True)

    # Make sure website text is available
    logger.info("Starting Midvale Community Clinic Chatbot application")
    
    # Make sure website text is available
    _ = get_website_text()
    
    # Run the Flask app
    app.run(debug=True)
