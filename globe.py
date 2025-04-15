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
from phi.assistant import Assistant
import base64
import re
from datetime import datetime
import inspect  # Import inspect for modification

# Monkey patch inspect.getargspec with inspect.getfullargspec
def getargspec_patch(func):
    fullargspec = inspect.getfullargspec(func)
    return inspect.ArgSpec(
        args=fullargspec.args,
        varargs=fullargspec.varargs,
        keywords=fullargspec.varkw,
        defaults=fullargspec.defaults,
    )

# Apply the monkey patch
inspect.getargspec = getargspec_patch

# Get API keys from environment variables
exa_api_key = os.environ.get("EXA_API_KEY")
groq_api_key = os.environ.get("GROQ_API_KEY")

# Define tools list for the Agent - simplified to only use Exa and DuckDuckGo
def create_tools_list():
    tools = []
    # Add Exa if API key is available
    if exa_api_key:
        tools.append(ExaTools(api_key=exa_api_key))
    # Always add DuckDuckGo as it doesn't require an API key
    tools.append(DuckDuckGo())
    return tools

# Create the agents with error handling for API keys
if groq_api_key:
    globe_hopper_agent = Agent(
        name="Globe Hopper",
        model=Groq(id="deepseek-r1-distill-llama-70b", api_key=groq_api_key),
        tools=create_tools_list(),
        markdown=True,
        description="You are an expert itinerary planning agent. Your role is to assist users in creating detailed, customized travel plans tailored to their preferences and needs.",
        instructions=[
            "Use Exa to search and extract relevant data from reputable travel platforms including flight information, schedules, and prices.",
            "Use DuckDuckGo to find up-to-date information about destinations.",
            "Use Exa to search for information about airports, flights, and transportation options.",
            "Collect information on flights, accommodations, local attractions, and estimated costs from these sources.",
            "Ensure that the gathered data is accurate and tailored to the user's preferences, such as destination, group size, and budget constraints.",
            "Create a clear and concise itinerary that includes: detailed day-by-day travel plan, suggested transportation and accommodation options, activity recommendations (e.g., sightseeing, dining, events), an estimated cost breakdown (covering transportation, accommodation, food, and activities).",
            "Present flight options with prices, departure/arrival times, and airlines when available based on Exa search results.",
            "If a particular website or travel option is unavailable, provide alternatives from other trusted sources.",
            "Use INR for all price calculations and mentions.",
        ],
    )
    chat_agent = Agent(
        name="Chat Bot",
        model=Groq(id="llama-3.3-70b-versatile", api_key=groq_api_key),
        tools=[DuckDuckGo()],
        markdown=True,
    )
else:
    globe_hopper_agent = None
    chat_agent = None

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
    for element in soup.find_all(['h1', 'h2', 'h3', 'p', 'ul', 'li']):
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
            if additional_notes:
                query += f". Additional notes: {additional_notes}"
            query += ". Please include flight options, accommodations, daily activities, and all costs in INR. Use Exa to search for flight information, prices, and schedules."
            return query
        if generate_plan:
            user_prompt = construct_query()
            if destination and start_date and end_date:  # Basic validations
                with st.spinner("✨ Crafting your perfect itinerary..."):
                    st.session_state.messages.append({"role": "user", "content": user_prompt})
                    try:
                        response = globe_hopper_agent.run(user_prompt)
                        # Ensure the content is a string
                        response_content = str(response.content) if hasattr(response, 'content') else "No response generated."
                        st.session_state.messages.append({"role": "assistant", "content": response_content})
                    except Exception as e:
                        st.error(f"Error fetching response: {str(e)}")
            else:
                st.warning("Please fill in at least the destination and travel dates.")
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
                        st.info(
    f"**You asked:**\n"
    f"{query}"
)
                        # Process the Markdown response to add our custom CSS classes
                        processed_response = response
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
                        <div style="padding: 10px; border-radius: 10px; max-width: 70%;">
                            {message["content"]}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div style="display: flex; justify-content: flex-start; margin-bottom: 10px;">
                        <div style="padding: 10px; border-radius: 10px; max-width: 70%;">
                            {message["content"]}
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