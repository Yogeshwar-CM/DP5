import streamlit as st
import requests
import os

# Get API key from environment variable
serpapi_api_key = os.environ.get("SERPAPI_API_KEY")

st.title("SerpAPI Image Search Test")

# Input for search query
search_query = st.text_input("Enter search term for images:", "Paris travel")

if st.button("Search Images") and serpapi_api_key:
    try:
        params = {
            "q": search_query,
            "tbm": "isch",  # Image search
            "api_key": serpapi_api_key
        }
        
        st.write("Searching for images...")
        response = requests.get("https://serpapi.com/search", params=params)
        results = response.json()
        
        st.write("Raw API response (first 1000 chars):")
        st.text(str(results)[:1000] + "...")  # Show partial response for debugging
        
        if 'images_results' in results:
            st.success(f"Found {len(results['images_results'])} images!")
            
            # Display first 3 images
            for i, img_result in enumerate(results['images_results'][:3]):
                img_url = img_result.get('original') or img_result.get('thumbnail')
                if img_url:
                    st.subheader(f"Image {i+1}")
                    st.image(img_url, caption=f"Result {i+1}", use_column_width=True)
                    st.write(f"Source: {img_result.get('source', 'Unknown')}")
                    st.write(f"Title: {img_result.get('title', 'No title')}")
                else:
                    st.warning(f"No valid URL found for image {i+1}")
        else:
            st.error("No images found in response. Check API key and response structure.")
            
    except Exception as e:
        st.error(f"Error: {str(e)}")
elif not serpapi_api_key:
    st.error("SERPAPI_API_KEY environment variable not found!")