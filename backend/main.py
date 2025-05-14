from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from PIL import Image
import openai
import io
import base64
import os
from typing import List, Dict
import json
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

STANDARD_NO_DRINKS_MSG = "No drinks were found in your request to analyze the picture for menu information. Please provide a menu image."

app = FastAPI()

# Allow frontend to access backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://drinks-nutrition-app.vercel.app"],  # Your Vercel URL
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize OpenAI client
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.get("/test-api-key")
async def test_api_key():
    """Test endpoint to verify OpenAI API key is loaded correctly."""
    try:
        # Try to make a simple API call to verify the key
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",  # Using a cheaper model for testing
            messages=[{"role": "user", "content": "Say 'API key is working!'"}],
            max_tokens=10
        )
        return {
            "status": "success",
            "message": "API key is working!",
            "response": response.choices[0].message.content
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

@app.get("/list-models")
async def list_models():
    """List available OpenAI models."""
    try:
        models = client.models.list()
        return {
            "status": "success",
            "models": [model.id for model in models.data]
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

def encode_image_to_base64(image: Image.Image) -> str:
    """Convert PIL Image to base64 string."""
    buffered = io.BytesIO()
    
    # Convert RGBA to RGB if necessary
    if image.mode in ('RGBA', 'LA'):
        background = Image.new('RGB', image.size, (255, 255, 255))
        background.paste(image, mask=image.split()[-1])  # Use alpha channel as mask
        image = background
    
    # Save as JPEG
    image.save(buffered, format="JPEG", quality=95)
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

@app.post("/upload/")
async def upload_menu(file: UploadFile = File(...)):
    try:
        # Read image
        image_bytes = await file.read()
        image = Image.open(io.BytesIO(image_bytes))
        
        # Convert image to base64
        base64_image = encode_image_to_base64(image)

        # Prepare the prompt for OpenAI
        prompt = """Extract drink data from this menu image. Output JSON:
        {
            "count": int,
            "drinks": [
                {
                "name": "string",
                "price": "string (no $)",
                "alcoholic_ingredients": "comma-separated string",
                "non_alcoholic_ingredients": "comma-separated string",
                "alcohol_oz": float (estimated pure alcohol content),
                "calories": int (estimated)
                }
            ]
        }

        Instructions:
        - Include all drinks: cocktails, beers, wines, spirits
        - Estimate `alcohol_oz` from ABV * volume (lookup if needed)
        - Estimate `calories` from ingredients and likely amounts (lookup if needed)
        - Use `null` if uncertain. Return only JSON

        Search the internet for nutrition facts of ingredients you don't know.
        Use the name of beers/wines/spirits to search the internet and use alcohol percentage to calculate the alcohol content in oz. 
        """

        # Call OpenAI API with GPT-4 Vision
        response = client.chat.completions.create(
            model="gpt-4.1-mini",  # Updated to current model name
            messages=[
                {
                    "role": "system",
                    "content": """You are an expert nutritionist and research nutrition facts carefully before providing a response.
                    If no drinks are found, reply with: 'No drinks found. Please provide a menu image.'"""
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=4000
        )

        # Extract and parse the JSON response
        content = response.choices[0].message.content
        
        # Log the raw response for debugging
        print("Raw GPT response:", content)
        
        try:
            # Try to parse the entire response first
            data = json.loads(content)
        except json.JSONDecodeError as json_err:
            print(f"JSON parsing error: {str(json_err)}")
            print(f"Error location: line {json_err.lineno}, column {json_err.colno}")
            print(f"Error position: {json_err.pos}")
            
            # If that fails, try to extract JSON portion
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = content[json_start:json_end]
                print("Extracted JSON string:", json_str)
                try:
                    data = json.loads(json_str)
                except json.JSONDecodeError as inner_err:
                    print(f"Second JSON parsing error: {str(inner_err)}")
                    # Try to find the last complete drink entry
                    last_complete_drink = json_str.rfind('},')
                    if last_complete_drink > 0:
                        # Add the closing brackets for the drinks array and main object
                        truncated_json = json_str[:last_complete_drink + 1] + ']}'
                        print("Truncated JSON:", truncated_json)
                        try:
                            data = json.loads(truncated_json)
                        except json.JSONDecodeError as final_err:
                            # If all parsing fails, return the raw message as an error
                            return JSONResponse(content={"error": STANDARD_NO_DRINKS_MSG})
                    else:
                        # If all parsing fails, return the raw message as an error
                        return JSONResponse(content={"error": STANDARD_NO_DRINKS_MSG})
            else:
                # If all parsing fails, return the raw message as an error
                return JSONResponse(content={"error": STANDARD_NO_DRINKS_MSG})
        
        return JSONResponse(content=data)

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Error processing image: {str(e)}"}
        )
