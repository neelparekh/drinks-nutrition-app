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

app = FastAPI()

# Allow frontend to access backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://menu-frontend.vercel.app"],  # Your Vercel URL
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
        prompt = """Analyze this menu image and extract drink information. First, list all drink names you see. Then, for each, provide the details in the JSON format. For each drink, provide:
        - name
        - price
        - alcoholic ingredients (comma-separated list)
        - non-alcoholic ingredients (comma-separated list)
        - estimated pure alcohol content in oz
        - estimated calories

        Return the data in this exact JSON format:
        {
            "drinks": [
                {
                    "name": "string",
                    "price": "string",
                    "alcoholic_ingredients": "string",
                    "non_alcoholic_ingredients": "string",
                    "alcohol_oz": float,
                    "calories": integer
                }
            ]
        }

        Be sure to include all beers, wines, and spirits. 
        If you don't know the ingredients, use the name and search the internet for the ingredients.
        For alcohol content of beers/wines/spirits, use the name and search the internet for the alcohol percentage and calculate thecontent in oz. 
        For calories, provide your best estimate based on ingredients, estimated amounts,and whether it's likely to be a syrup.
        If you're unsure about any value, use null. 
        Drop the currency symbol for prices.
        """

        # Call OpenAI API with GPT-4 Vision
        response = client.chat.completions.create(
            model="gpt-4.1-mini",  # Updated to current model name
            messages=[
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
                            raise ValueError(f"Failed to parse truncated JSON: {str(final_err)}")
                    else:
                        raise ValueError("Could not find any complete drink entries in the response")
            else:
                raise ValueError("No valid JSON found in response")
        
        return JSONResponse(content=data)

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Error processing image: {str(e)}"}
        )
