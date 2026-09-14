import streamlit as st
import tempfile
import os
import serpapi
import google.generativeai as genai
import concurrent.futures
import re

st.set_page_config(page_title="Valuation Engine", layout="wide")

st.title("Secondary Market Valuation Tool")
st.write("Search by photo or text to identify an item, pull its history, and check active vs. sold prices.")

# Sidebar API Keys
st.sidebar.header("API Keys")
serp_api_key = st.sidebar.text_input("Enter SerpApi Key", type="password")
gemini_api_key = st.sidebar.text_input("Enter Gemini API Key", type="password")
st.sidebar.markdown("*Get free keys at [SerpApi](https://serpapi.com) and [Google AI Studio](https://aistudio.google.com)*")

def clean_query(title):
    cleaned = re.sub(r'[^\w\s-]', '', title)
    words = cleaned.split()
    return " ".join(words[:5])

@st.cache_data(ttl=3600, show_spinner=False)
def get_active_ebay(api_key, raw_query):
    short_query = clean_query(raw_query)
    client = serpapi.Client(api_key=api_key, timeout=15)
    return client.search({"engine": "ebay", "_nkw": short_query}), short_query

@st.cache_data(ttl=3600, show_spinner=False)
def get_sold_ebay_via_google(api_key, raw_query):
    """Uses Google search indexing for eBay sold items—bypasses eBay anti-scraping blocks."""
    short_query = clean_query(raw_query)
    client = serpapi.Client(api_key=api_key, timeout=15)
    # Search Google for indexed sold listings on eBay
    params = {
        "engine": "google",
        "q": f'site:ebay.com/itm "{short_query}" "Sold"',
        "num": 5
    }
    return client.search(params), short_query

input_method = st.radio("Choose Input Method", ("Text Search", "Take Photo", "File Upload"))
product_title = ""

# --- INPUT LOGIC ---
if input_method == "Text Search":
    search_query = st.text_input("Enter Make and Model (e.g., Allen Bradley PowerFlex 525)")
    if st.button("Search") and search_query:
        product_title = search_query

elif input_method in ["Take Photo", "File Upload"]:
    if input_method == "File Upload":
        image_file = st.file_uploader("Upload an image", type=["jpg", "jpeg", "png", "webp"])
    else:
        image_file = st.camera_input("Take a picture")

    if image_file and serp_api_key:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            tmp.write(image_file.getvalue())
            tmp_path = tmp.name

        st.image(image_file, caption="Image captured", width=400)
        
        with st.spinner("Analyzing image with Google Lens..."):
            try:
                client = serpapi.Client(api_key=serp_api_key, timeout=20)
                upload_response = client.upload_image(tmp_path)
                lens_results = client.search({
                    "engine": "google_lens",
                    "image_id": upload_response["image_id"]
                })
                
                visual_matches = lens_results.get("visual_matches", [])
                if visual_matches:
                    product_title = visual_matches[0].get("title", "")
                else:
                    st.error("No clear products identified. Try text search.")
                    
            except Exception as e:
                st.error(f"Vision API Error: {e}")
            finally:
                os.remove(tmp_path)

# --- ANALYSIS LOGIC ---
if product_title:
    st.success(f"**Target Item:** {product_title}")
    st.markdown("---")

    # 1. Manufacturing History (Gemini)
    if gemini_api_key:
        st.subheader("Manufacturing History")
        with st.spinner("Pulling item background..."):
            try:
                genai.configure(api_key=gemini_api_key)
                model = genai.GenerativeModel("gemini-3.6-flash")
                prompt = f"""
                You are an expert appraiser. I am researching this item: '{product_title}'.
                Provide a short summary containing:
                - Years manufactured
                - Country of origin
                - A 2-sentence summary of its reputation or notable features.
                Keep it highly concise and formatted with bullet points.
                """
                response = model.generate_content(prompt)
                st.write(response.text)
            except Exception as e:
                st.error(f"History API Error: {e}")
    else:
        st.info("Enter a Gemini API key in the sidebar to unlock manufacturing history.")
        
    st.markdown("---")
    
    # 2. Parallel Market Search (eBay Active + Google-Indexed eBay Sold)
    if serp_api_key:
        col1, col2 = st.columns(2)
        
        with st.spinner("Fetching active and sold listings..."):
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future_active = executor.submit(get_active_ebay, serp_api_key, product_title)
                future_sold = executor.submit(get_sold_ebay_via_google, serp_api_key, product_title)
                
                try:
                    active_results, active_query = future_active.result(timeout=20)
                except Exception as e:
                    active_results, active_query = e, clean_query(product_title)

                try:
                    sold_results, sold_query = future_sold.result(timeout=20)
                except Exception as e:
                    sold_results, sold_query = e, clean_query(product_title)

        with col1:
            st.subheader("Active Asking Prices")
            st.caption(f"Search term: *{active_query}*")
            if isinstance(active_results, Exception):
                st.warning("Active listings search timed out.")
            else:
                active_items = active_results.get("organic_results", [])
                if not active_items:
                    st.write("No active listings found.")
                else:
                    for item in active_items[:5]:
                        price = item.get("price", {}).get("raw", "Unknown") if isinstance(item.get("price"), dict) else "Unknown"
                        title = item.get("title", "Unknown item")
                        st.markdown(f"- **{price}** | {title}")

        with col2:
            st.subheader("Completed Sold Prices")
            st.caption(f"Search term: *{sold_query}*")
            if isinstance(sold_results, Exception):
                st.warning("Sold listings search timed out.")
            else:
                # Process Google organic search results for eBay sold items
                sold_items = sold_results.get("organic_results", [])
                if not sold_items:
                    st.write("No completed sales found.")
                else:
                    for item in sold_items[:5]:
                        title = item.get("title", "Unknown item")
                        snippet = item.get("snippet", "")
                        link = item.get("link", "#")
                        st.markdown(f"- [{title}]({link})")
                        if snippet:
                            st.caption(snippet[:120] + "...")
