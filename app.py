import streamlit as st
import tempfile
import os
import serpapi
import google.generativeai as genai

st.set_page_config(page_title="Valuation Engine", layout="wide")

st.title("Secondary Market Valuation Tool")
st.write("Search by photo or text to identify an item, pull its history, and check active vs. sold prices.")

# Securely take the API keys in the sidebar
st.sidebar.header("API Keys")
serp_api_key = st.sidebar.text_input("Enter SerpApi Key", type="password")
gemini_api_key = st.sidebar.text_input("Enter Gemini API Key", type="password")
st.sidebar.markdown("*Get free keys at [SerpApi](https://serpapi.com) and [Google AI Studio](https://aistudio.google.com)*")

# Let the user choose how to search
input_method = st.radio("Choose Input Method", ("Text Search", "Take Photo", "File Upload"))

product_title = ""

# --- INPUT LOGIC ---
if input_method == "Text Search":
    search_query = st.text_input("Enter Make and Model (e.g., Pioneer HPM-100 speaker)")
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
                client = serpapi.Client(api_key=serp_api_key)
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

    # 1. Pull Manufacturing History using Gemini
    if gemini_api_key:
        st.subheader("Manufacturing History")
        with st.spinner("Pulling item background..."):
            try:
                genai.configure(api_key=gemini_api_key)
                model = genai.GenerativeModel("gemini-2.5-flash")
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
    
    # 2. Pull Market Prices using SerpApi
    if serp_api_key:
        col1, col2 = st.columns(2)
        client = serpapi.Client(api_key=serp_api_key)
        
        with col1:
            st.subheader("Active Asking Prices")
            with st.spinner("Fetching active listings..."):
                try:
                    active_results = client.search({"engine": "ebay", "_nkw": product_title})
                    active_items = active_results.get("organic_results", [])
                    
                    if not active_items:
                        st.write("No active listings found.")
                    else:
                        for item in active_items[:5]:
                            price = item.get("price", {}).get("raw", "Unknown") if isinstance(item.get("price"), dict) else "Unknown"
                            title = item.get("title", "Unknown item")
                            st.markdown(f"- **{price}** | {title}")
                except Exception as e:
                    st.error(f"Market API Error: {e}")

        with col2:
            st.subheader("Completed Sold Prices")
            with st.spinner("Fetching historical sales..."):
                try:
                    sold_results = client.search({"engine": "ebay", "_nkw": product_title, "show_only": "Sold"})
                    sold_items = sold_results.get("organic_results", [])
                    
                    if not sold_items:
                        st.write("No completed sales found.")
                    else:
                        for item in sold_items[:5]:
                            price = item.get("price", {}).get("raw", "Unknown") if isinstance(item.get("price"), dict) else "Unknown"
                            title = item.get("title", "Unknown item")
                            st.markdown(f"- **{price}** | {title}")
                except Exception as e:
                    st.error(f"Market API Error: {e}")
