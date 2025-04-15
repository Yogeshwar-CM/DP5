import streamlit as st
import os
from phi.agent import Agent
import io
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.units import inch
import markdown
import html2text
from bs4 import BeautifulSoup
from phi.model.groq import Groq
from phi.tools.exa import ExaTools
from phi.tools.duckduckgo import DuckDuckGo
from phi.tools.serpapi_tools import SerpApiTools
from phi.assistant import Assistant
import base64
import re
from datetime import datetime
from PIL import Image as PILImage
import requests
from io import BytesIO

# Get API keys from environment variables
exa_api_key = os.environ.get("EXA_API_KEY")
groq_api_key = os.environ.get("GROQ_API_KEY")
serpapi_api_key = os.environ.get("SERPAPI_API_KEY")  # For image search

# Define tools list for the Agent - now including image search
def create_tools_list():
    tools = []
    
    # Add Exa if API key is available
    if exa_api_key:
        tools.append(ExaTools(api_key=exa_api_key))
    
    # Add SerpApi for image search if API key is available
    if serpapi_api_key:
        tools.append(SerpApiTools(api_key=serpapi_api_key))
    
    # Always add DuckDuckGo as it doesn't require an API key
    tools.append(DuckDuckGo())
    
    return tools

# Create the agents with error handling for API keys
if groq_api_key:
    globe_hopper_agent = Agent(
        name="Globe Hopper",
        model=Groq(id="deepseek-r1-distill-llama-70b", api_key=groq_api_key),
        tools=create_tools_list(),
        debug_mode=True,  # This will show more detailed logs
        show_tool_calls=True,  # This will show when tools are being used
        markdown=True,
        description="You are an expert itinerary planning agent. Your role is to assist users in creating detailed, customized travel plans tailored to their preferences and needs.",
        instructions=[
            "Use Exa to search and extract relevant data from reputable travel platforms including flight information, schedules, and prices.",
            "Use DuckDuckGo to find up-to-date information about destinations.",
            "Use Exa to search for information about airports, flights, and transportation options.",
            "Use SerpApi to find relevant images of destinations, attractions, and accommodations to include in the itinerary.",
            "When including images, make sure they are relevant and high quality. Always provide proper attribution if available.",
            "Collect information on flights, accommodations, local attractions, and estimated costs from these sources.",
            "Ensure that the gathered data is accurate and tailored to the user's preferences, such as destination, group size, and budget constraints.",
            "Create a clear and concise itinerary that includes: detailed day-by-day travel plan, suggested transportation and accommodation options, activity recommendations (e.g., sightseeing, dining, events), an estimated cost breakdown (covering transportation, accommodation, food, and activities).",
            "Present flight options with prices, departure/arrival times, and airlines when available based on Exa search results.",
            "If a particular website or travel option is unavailable, provide alternatives from other trusted sources.",
            "Use INR for all price calculations and mentions.",
            "Include relevant images where appropriate to enhance the itinerary presentation.",
        ],
    )

    chat_agent = Agent(
        name="Chat Bot",
        model=Groq(id="llama-3.3-70b-versatile", api_key=groq_api_key),
        tools=create_tools_list(),
        markdown=True,
    )
else:
    globe_hopper_agent = None
    chat_agent = None

def display_images_from_markdown(markdown_text, destination=None):
    """Extract and display images from markdown text with better handling"""
    if not destination:
        # Try to extract destination from markdown if not provided
        dest_match = re.search(r'Plan a trip to (.*?) for', markdown_text)
        destination = dest_match.group(1) if dest_match else None
    
    # Find all markdown image tags ![alt text](url)
    image_matches = re.finditer(r'!\[(.*?)\]\((.*?)\)', markdown_text)
    
    # If no images found but we have a destination, try to get some
    if not list(image_matches) and destination and serpapi_api_key:
        try:
            # Use SerpApi to find images for the destination
            search_query = f"{destination} travel attractions"
            params = {
                "q": search_query,
                "tbm": "isch",  # image search
                "api_key": serpapi_api_key
            }
            response = requests.get("https://serpapi.com/search", params=params)
            results = response.json()
            
            # Display first 3 images
            if 'images_results' in results:
                for i, img_result in enumerate(results['images_results'][:3]):
                    img_url = img_result.get('original')
                    if img_url:
                        try:
                            st.image(img_url, 
                                    caption=f"{destination} attraction {i+1}",
                                    use_column_width=True)
                        except:
                            continue
        except Exception as e:
            st.warning(f"Couldn't fetch additional images: {str(e)}")
    
    # Process the original markdown images
    image_matches = re.finditer(r'!\[(.*?)\]\((.*?)\)', markdown_text)
    for match in image_matches:
        alt_text = match.group(1)
        image_url = match.group(2)
        
        try:
            st.image(image_url, 
                    caption=alt_text if alt_text else "Travel Image",
                    use_column_width=True)
            markdown_text = markdown_text.replace(match.group(0), "")
        except:
            continue
    
    return markdown_text



def get_pdf_download_link(markdown_text, filename, destination, travel_dates):
    """Generate a download link for a PDF version of the itinerary"""
    # Create a PDF in memory
    buffer = io.BytesIO()
    
    # Set up the PDF document
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []
    
    # Set up styles
    styles = getSampleStyleSheet()
    title_style = styles['Title']
    heading_style = styles['Heading1']
    subheading_style = styles['Heading2']
    normal_style = styles['Normal']
    
    # Custom styles
    section_style = ParagraphStyle(
        'SectionStyle',
        parent=styles['Heading2'],
        textColor=colors.blue,
        spaceAfter=12
    )
    
    day_style = ParagraphStyle(
        'DayStyle',
        parent=styles['Heading3'],
        textColor=colors.navy,
        backColor=colors.lightgrey,
        borderPadding=5,
        spaceAfter=10
    )
    
    bullet_style = ParagraphStyle(
        'BulletStyle',
        parent=styles['Normal'],
        leftIndent=20,
        spaceAfter=5
    )
    
    # Add a header
    elements.append(Paragraph(f"Travel Itinerary to {destination}", title_style))
    elements.append(Spacer(1, 0.2*inch))
    elements.append(Paragraph(f"Travel Dates: {travel_dates}", subheading_style))
    elements.append(Spacer(1, 0.3*inch))
    
    # Convert markdown to HTML
    html_content = markdown.markdown(markdown_text)
    
    # Parse HTML with BeautifulSoup
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Process the HTML content into reportlab elements
    current_section = None
    
    for element in soup.find_all(['h1', 'h2', 'h3', 'p', 'ul', 'li', 'img']):
        if element.name == 'h1':
            elements.append(Paragraph(element.text, heading_style))
            elements.append(Spacer(1, 0.1*inch))
        elif element.name == 'h2':
            elements.append(Paragraph(element.text, section_style))
            elements.append(Spacer(1, 0.1*inch))
        elif element.name == 'h3':
            elements.append(Paragraph(element.text, day_style))
        elif element.name == 'p':
            elements.append(Paragraph(element.text, normal_style))
            elements.append(Spacer(1, 0.05*inch))
        elif element.name == 'ul':
            # Skip the ul tag itself, we'll process the li tags
            pass
        elif element.name == 'li':
            elements.append(Paragraph(f"• {element.text}", bullet_style))
        elif element.name == 'img':
            try:
                img_url = element.get('src')
                response = requests.get(img_url, stream=True, timeout=5)
                if response.status_code == 200:
                    img_data = BytesIO(response.content)
                    pil_img = PILImage.open(img_data)
                    
                    # Resize image to fit PDF while maintaining aspect ratio
                    max_width = 400  # points (about 5.5 inches)
                    width_percent = (max_width / float(pil_img.width))
                    height = int((float(pil_img.height) * float(width_percent)))
                    
                    img_buffer = BytesIO()
                    pil_img.save(img_buffer, format='PNG')
                    img_buffer.seek(0)
                    
                    # Add image to PDF with dynamic sizing
                    rl_img = Image(img_buffer, width=max_width, height=height)
                    elements.append(rl_img)
                    
                    # [Rest of the image handling code...]
            except Exception as e:
                st.warning(f"Couldn't include image in PDF: {str(e)}")
                continue  # Skip this image but continue with the rest
    
    # If no elements were created from the HTML parsing, add raw text as paragraphs
    if len(elements) <= 4:  # Only header elements present
        # Split by lines and add as paragraphs
        for line in markdown_text.split('\n'):
            if line.strip():
                elements.append(Paragraph(line, normal_style))
                elements.append(Spacer(1, 0.05*inch))
    
    # Add a footer
    elements.append(Spacer(1, 0.5*inch))
    elements.append(Paragraph("Generated by GlobeTrek - Your AI Travel Companion", 
                             ParagraphStyle('Footer', alignment=1, textColor=colors.grey)))
    
    # Build the PDF
    doc.build(elements)
    
    # Get the PDF data and encode it
    pdf_data = buffer.getvalue()
    buffer.close()
    
    b64 = base64.b64encode(pdf_data).decode()
    
    # Create download link
    href = f'<a href="data:application/pdf;base64,{b64}" download="{filename}" class="download-button">Download PDF Itinerary</a>'
    return href

# Define CSS for better UI with download button styles
def set_custom_styles():
    st.markdown("""
    <style>
    .stButton button {
        background-color: #4a86e8;
        color: white;
        font-weight: bold;
        border-radius: 5px;
        padding: 0.5rem 1rem;
        width: 100%;
    }
    .stButton button:hover {
        background-color: #3a76d8;
    }
    .card {
        border-radius: 10px;
        padding: 20px;
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        margin-bottom: 20px;
    }
    .trip-header {
        border-left: 5px solid #4a86e8;
        padding: 15px;
        margin-bottom: 20px;
        border-radius: 5px;
    }
    .section-title {
        color: #4a86e8;
        font-weight: bold;
        margin-bottom: 10px;
    }
    .itinerary-container {
        border-radius: 8px;
        border: 1px solid #e0e0e0;
        margin-bottom: 20px;
        overflow: hidden;
    }
    .itinerary-header {
        background-color: #4a86e8;
        color: white;
        padding: 15px;
        font-size: 18px;
        font-weight: bold;
    }
    .itinerary-content {
        padding: 20px;
    }
    .day-card {
        background-color: #f9f9f9;
        border-radius: 8px;
        padding: 15px;
        margin-bottom: 15px;
        border-left: 4px solid #4a86e8;
    }
    .day-title {
        font-weight: bold;
        color: #4a86e8;
        margin-bottom: 10px;
        border-bottom: 1px solid #e0e0e0;
        padding-bottom: 5px;
    }
    .activity-item {
        margin-bottom: 8px;
        padding-left: 10px;
    }
    .flight-card {
        border-radius: 8px;
        padding: 15px;
        margin-bottom: 15px;
        border: 1px solid #d0e1f9;
    }
    .accommodation-card {
        border-radius: 8px;
        padding: 15px;
        margin-bottom: 15px;
        border: 1px solid #d0f9e0;
    }
    .cost-card {
        border-radius: 8px;
        padding: 15px;
        margin-bottom: 15px;
        border: 1px solid #f9e0d0;
    }
    .highlight-text {
        color: #4a86e8;
        font-weight: bold;
    }
    .download-button {
        display: inline-block;
        background-color: #28a745;
        color: white;
        text-decoration: none;
        padding: 10px 20px;
        border-radius: 5px;
        font-weight: bold;
        margin-top: 10px;
        text-align: center;
        transition: background-color 0.3s;
    }
    .download-button:hover {
        background-color: #218838;
        color: white;
    }
    .download-section {
        margin-top: 15px;
        text-align: center;
    }
    .travel-image {
        border-radius: 8px;
        margin: 10px 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    </style>
    """, unsafe_allow_html=True)

# Set up Streamlit UI
st.set_page_config(layout="wide", page_title="GlobeTrek - Your AI Travel Companion", page_icon="✈️")
set_custom_styles()

st.markdown("""
<div style="text-align: center">
    <h1 style="color: #4a86e8;">✈️ GlobeTrek</h1>
    <p style="font-size: 1.2em; margin-bottom:20px;">Your AI-powered travel planning assistant</p>
</div>
""", unsafe_allow_html=True)

# Check for missing API keys and show warnings
missing_keys = []
if not groq_api_key:
    missing_keys.append("GROQ_API_KEY")
if not exa_api_key:
    missing_keys.append("EXA_API_KEY")
if not serpapi_api_key:
    missing_keys.append("SERPAPI_API_KEY")

if missing_keys:
    st.warning(f"⚠️ The following environment variables are missing: {', '.join(missing_keys)}. Some features may not work properly.")

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []

# Create tabs with better styling
travel_tab, chat_tab = st.tabs(["🧳 Plan Your Trip", "💬 Chat"])

# Travel Plan tab
with travel_tab:
    if not globe_hopper_agent:
        st.error("⚠️ GROQ API key is missing. Travel planning is unavailable.")
    else:
        st.markdown('<div class="trip-header"><h2>Create Your Dream Itinerary</h2><p>Fill in the details below to get a personalized travel plan</p></div>', unsafe_allow_html=True)
        
        # Use columns for a cleaner layout
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown('<div class="section-title">Basic Travel Details</div>', unsafe_allow_html=True)
            
            origin_city = st.text_input("Departure City", 
                                        placeholder="Where are you departing from?", 
                                        help="City name you're departing from")
            destination = st.text_input("Destination", 
                                        placeholder="Where do you want to go?",
                                        help="City, country or region you want to visit")
            
            col1a, col1b = st.columns(2)
            with col1a:
                start_date = st.date_input("Departure Date")
            with col1b:
                end_date = st.date_input("Return Date")
                
            travelers = st.number_input("Number of Travelers", min_value=1, value=2, step=1)
            st.markdown('</div>', unsafe_allow_html=True)
        
        with col2:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown('<div class="section-title">Travel Preferences</div>', unsafe_allow_html=True)
            
            # Budget selection with radio buttons
            budget_option = st.radio(
                "Budget Range", 
                ["Budget - Up to ₹50,000", "Mid-range - ₹50,000 to ₹1,50,000", "Luxury - Above ₹1,50,000"],
                horizontal=True
            )
            
            # Travel interests as multi-select
            interests = st.multiselect(
                "Travel Interests",
                ["Adventure", "Relaxation", "Cultural", "Food & Cuisine", "Shopping", "Nature", "Historical Sites", "Nightlife", "Family-friendly"],
                default=["Adventure", "Cultural"]
            )
            
            # Accommodation preferences
            accommodation = st.selectbox(
                "Preferred Accommodation",
                ["Budget Hostels", "Mid-range Hotels", "Luxury Resorts", "Homestays/Airbnb", "Any"]
            )
            
            # Add option to include images
            include_images = st.checkbox("Include destination images in itinerary", value=True)
            
            additional_notes = st.text_area("Additional Requirements", 
                                           placeholder="Any special needs or specific places you want to visit?")
            st.markdown('</div>', unsafe_allow_html=True)
        
        # Create plan button with better styling
        plan_col1, plan_col2, plan_col3 = st.columns([1, 2, 1])
        with plan_col2:
            generate_plan = st.button("🚀 Generate My Travel Plan", use_container_width=True)
        
        # Construct the full query with all the new inputs
        def construct_query():
            if not destination:
                return ""
            
            # Format the dates properly
            travel_dates = f"{start_date.strftime('%b %d, %Y')} to {end_date.strftime('%b %d, %Y')}"
            
            # Extract the budget range from the selection
            budget_map = {
                "Budget - Up to ₹50,000": "under ₹50,000",
                "Mid-range - ₹50,000 to ₹1,50,000": "₹50,000-1,50,000",
                "Luxury - Above ₹1,50,000": "over ₹1,50,000"
            }
            budget_str = budget_map.get(budget_option, "flexible")
            
            # Build the query
            query = f"Plan a trip to {destination} for {travelers} travelers"
            
            if origin_city:
                query += f" departing from {origin_city}"
                
            query += f" from {travel_dates} with a {budget_str} budget in INR"
            
            if interests:
                query += f". We're interested in: {', '.join(interests)}"
                
            if accommodation != "Any":
                query += f". We prefer staying in {accommodation}"
                
            if include_images:
                query += ". Please include relevant images of destinations, attractions, and accommodations where appropriate."
                
            if additional_notes:
                query += f". Additional notes: {additional_notes}"
                
            query += ". Please include flight options, accommodations, daily activities, and all costs in INR. Use Exa to search for flight information, prices, and schedules."
            
            return query
        
        # In your generate_plan section, modify to pass destination:
        if generate_plan:
            user_prompt = construct_query()
            if destination and start_date and end_date:
                with st.spinner("✨ Crafting your perfect itinerary..."):
                    st.session_state.messages.append({"role": "user", "content": user_prompt})
                    try:
                        response = globe_hopper_agent.run(user_prompt)
                        response_content = str(response.content) if hasattr(response, 'content') else "No response generated."
                        st.session_state.messages.append({"role": "assistant", "content": response_content})
                        
                        # Display images separately using destination keywords
                        st.subheader("Destination Images")
                        image_keywords = f"{destination} {', '.join(interests) if interests else ''}"
                        display_images_from_markdown(response_content, destination=destination)
                        
                    except Exception as e:
                        st.error(f"Error fetching response: {str(e)}")

        # Display travel plan history with improved visual components
        if st.session_state.messages:
            st.markdown("""
            <div style="margin-top: 40px;">
                <h3 style="color: #4a86e8; border-bottom: 2px solid #4a86e8; padding-bottom: 10px;">
                    Your Travel Plans
                </h3>
            </div>
            """, unsafe_allow_html=True)
            
            for i in range(0, len(st.session_state.messages), 2):
                if i+1 < len(st.session_state.messages):  # Make sure we have both question and answer
                    query = st.session_state.messages[i]["content"]
                    response = st.session_state.messages[i+1]["content"]
                    
                    with st.expander(f"Travel Plan: {query[:50]}...", expanded=(i == len(st.session_state.messages)-2)):
                        st.info(f"**You asked:**\n{query}")
                        
                        # Process the Markdown response to display images and remove image tags
                        processed_response = display_images_from_markdown(response)
                        
                        # Create a unique filename with destination and date
                        destination_name = destination.replace(" ", "_") if destination else "travel_plan"
                        today_date = datetime.now().strftime("%Y%m%d")
                        filename = f"{destination_name}_itinerary_{today_date}.pdf"
                        
                        # Generate download link for PDF
                        travel_dates = f"{start_date.strftime('%b %d, %Y')} to {end_date.strftime('%b %d, %Y')}" if 'start_date' in locals() and 'end_date' in locals() else "Your trip"
                        download_link = get_pdf_download_link(response, filename, destination, travel_dates)
                        
                        # Wrap in our custom container class with download button
                        processed_response = f"""
                        <div class="itinerary-container">
                            <div class="itinerary-header">
                                🌟 Your Customized Travel Itinerary
                            </div>
                            <div class="itinerary-content">
                                {processed_response}
                                <div class="download-section">
                                    {download_link}
                                </div>
                            </div>
                        </div>
                        """
                        
                        st.markdown(processed_response, unsafe_allow_html=True)

# Chat tab with improved styling
with chat_tab:
    if not chat_agent:
        st.error("⚠️ GROQ API key is missing. Chat functionality is unavailable.")
    else:
        st.markdown('<div class="trip-header"><h2>Chat with our Travel Assistant</h2><p>Ask any travel-related questions or get recommendations</p></div>', unsafe_allow_html=True)
        
        # Display chat history in a card style
        st.markdown('<div class="card" style="max-height: 400px; overflow-y: auto;">', unsafe_allow_html=True)
        if not st.session_state.chat_messages:
            st.markdown("""
            <div style="text-align: center; padding: 20px; color: #888;">
                <p>No messages yet. Start chatting below!</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            for message in st.session_state.chat_messages:
                if message["role"] == "user":
                    st.markdown(f"""
                    <div style="display: flex; justify-content: flex-end; margin-bottom: 10px;">
                        <div style="background-color: #e3f2fd; padding: 10px; border-radius: 10px; max-width: 70%;">
                            {message["content"]}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    # Process assistant messages to display images
                    assistant_content = message["content"]
                    
                    # First display any images
                    assistant_content = display_images_from_markdown(assistant_content)
                    
                    st.markdown(f"""
                    <div style="display: flex; justify-content: flex-start; margin-bottom: 10px;">
                        <div style="background-color: #f5f5f5; padding: 10px; border-radius: 10px; max-width: 70%;">
                            {assistant_content}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Chat input with better styling
        st.markdown('<div class="card" style="margin-top: 20px;">', unsafe_allow_html=True)
        col1, col2 = st.columns([4, 1])
        with col1:
            user_message = st.text_input("Type your message...", key="chat_input", 
                                        placeholder="Ask me anything about travel...")
        with col2:
            send_button = st.button("Send 📤", use_container_width=True)
            
        if send_button and user_message:
            with st.spinner("Thinking..."):
                st.session_state.chat_messages.append({"role": "user", "content": user_message})
                try:
                    chat_response = chat_agent.run(user_message).content
                    st.session_state.chat_messages.append({"role": "assistant", "content": chat_response})
                    st.rerun()  # Refresh to show the new messages
                except Exception as e:
                    st.error(f"Error fetching response: {str(e)}")
        st.markdown('</div>', unsafe_allow_html=True)

# Add a footer
st.markdown("""
<div style="text-align: center; margin-top: 50px; padding: 20px; border-top: 1px solid #eee; color: #888;">
    <p>Powered by AI - GlobeTrek Travel Planner © 2025</p>
</div>
""", unsafe_allow_html=True)