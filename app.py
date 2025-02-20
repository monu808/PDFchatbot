import streamlit as st
import PyPDF2
import re
import pyttsx3
import threading
import time
import json
from typing import List, Tuple
from gtts import gTTS
import tempfile
import numpy as np  # NEW: For vector operations

# Optional libraries for OCR
try:
    from pdf2image import convert_from_bytes
    import pytesseract
except ImportError:
    st.warning("To enable OCR for scanned PDFs, please install 'pdf2image' and 'pytesseract' libraries.")

# For WebSocket client functionality
try:
    import websocket  # from 'websocket-client' package
except ImportError:
    st.warning("To enable real-time collaboration, please install the 'websocket-client' package.")

# For OpenAI API (ensure you have openai installed and your API key configured)
try:
    import openai
except ImportError:
    st.warning("To enable AI summarization and Q&A, please install the 'openai' package.")

# ------------------------------
# Helper Functions
# ------------------------------

def extract_pdf_text(file) -> Tuple[List[str], bool]:
    """
    Extract text from a PDF file.
    If the page text is empty, try using OCR to extract text from the page image.
    Returns a tuple (list of page texts, success flag).
    """
    try:
        reader = PyPDF2.PdfReader(file)
        pages_text = []
        
        # Read file bytes for OCR conversion
        file.seek(0)
        file_bytes = file.read()
        file.seek(0)  # Reset pointer for PyPDF2
        
        # Try to convert PDF pages to images for OCR if available
        try:
            images = convert_from_bytes(file_bytes)
        except Exception as e:
            images = []
            st.warning("OCR conversion failed; make sure Poppler is installed properly.")
        
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if not text or not text.strip():
                # If text extraction failed, try OCR if we have an image
                if images and i < len(images):
                    try:
                        text = pytesseract.image_to_string(images[i])
                        if not text.strip():
                            text = f"Page {i+1} has no extractable text."
                    except Exception as e:
                        text = f"Error during OCR on Page {i+1}: {str(e)}"
                else:
                    text = f"Page {i+1} has no extractable text."
            pages_text.append(text)
        return pages_text, True
    except Exception as e:
        st.error(f"PDF Error: {str(e)}")
        return [f"Error processing PDF: {str(e)}"], False

def translate_text(text: str, dest_lang: str) -> str:
    """Translate text to the target language synchronously."""
    try:
        from googletrans import Translator
        translator = Translator()
        translated = translator.translate(text, dest=dest_lang)
        return translated.text
    except Exception as e:
        st.error(f"Translation Error: {str(e)}")
        return text

def text_to_speech(text):
    """Convert text to speech and return the audio file path."""
    tts = gTTS(text=text, lang="en")
    
    # Save audio in a temporary file
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    tts.save(temp_file.name)
    
    return temp_file.name

def summarize_text(text: str) -> str:
    """
    Use the OpenAI API to summarize the provided text.
    Make sure your API key is set in Streamlit secrets as OPENAI_API_KEY.
    """
    openai_api_key = st.secrets.get("OPENAI_API_KEY", None)
    if not openai_api_key:
        st.error("OpenAI API key not found in secrets. Please add it as OPENAI_API_KEY.")
        return "Summarization unavailable."
    
    openai.api_key = openai_api_key
    try:
        # Using GPT-3.5 Turbo for summarization
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that summarizes text concisely."},
                {"role": "user", "content": f"Summarize the following text:\n\n{text}"}
            ],
            max_tokens=150,
            temperature=0.5,
        )
        summary = response["choices"][0]["message"]["content"].strip()
        return summary
    except Exception as e:
        st.error(f"Error during summarization: {e}")
        return "Summarization failed."

def answer_question(question: str, pdf_pages: List[str]) -> Tuple[str, List[int]]:
    """
    Answer a question based on the document content.
    Performs a simple keyword-based search to find relevant pages,
    then sends the question along with the extracted context to the OpenAI API.
    Returns the answer and a list of relevant page numbers.
    """
    openai_api_key = st.secrets.get("OPENAI_API_KEY", None)
    if not openai_api_key:
        st.error("OpenAI API key not found in secrets. Please add it as OPENAI_API_KEY.")
        return "Answering unavailable.", []
    
    openai.api_key = openai_api_key
    # Identify relevant pages using a simple keyword search
    relevant_pages = []
    keywords = question.lower().split()
    for i, page in enumerate(pdf_pages):
        if any(keyword in page.lower() for keyword in keywords):
            relevant_pages.append(i+1)  # pages are 1-indexed for display
    context = "\n".join([pdf_pages[i-1] for i in relevant_pages]) if relevant_pages else "No specific context available."
    
    prompt = (
        f"Based on the following document content, answer the question: {question}\n\n"
        f"Document:\n{context}\n\n"
        "Please include citations like [Page X] where applicable."
    )
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that answers questions based on provided document content."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=250,
            temperature=0.5,
        )
        answer = response["choices"][0]["message"]["content"].strip()
        return answer, relevant_pages
    except Exception as e:
        st.error(f"Error during Q&A: {e}")
        return "An error occurred while processing your question.", relevant_pages

def generate_quiz(text: str, num_questions: int = 5) -> str:
    """
    Use the OpenAI API to generate a quiz based on the provided text.
    Returns the quiz questions and answers.
    """
    openai_api_key = st.secrets.get("OPENAI_API_KEY", None)
    if not openai_api_key:
        st.error("OpenAI API key not found in secrets. Please add it as OPENAI_API_KEY.")
        return "Quiz generation unavailable."
    
    openai.api_key = openai_api_key
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that generates quiz questions based on provided content."},
                {"role": "user", "content": f"Generate {num_questions} quiz questions with answers based on the following text:\n\n{text}"}
            ],
            max_tokens=500,
            temperature=0.7,
        )
        quiz_content = response["choices"][0]["message"]["content"].strip()
        return quiz_content
    except Exception as e:
        st.error(f"Error during quiz generation: {e}")
        return "Quiz generation failed."

# ------------------------------
# New Feature: Semantic Search Helpers
# ------------------------------

def compute_page_embeddings(pdf_pages: List[str]) -> List[List[float]]:
    """
    Compute embeddings for each page using OpenAI's embedding model.
    """
    openai_api_key = st.secrets.get("OPENAI_API_KEY", None)
    if not openai_api_key:
        st.error("OpenAI API key not found for computing embeddings.")
        return []
    openai.api_key = openai_api_key
    embeddings = []
    for page in pdf_pages:
        try:
            response = openai.Embedding.create(model="text-embedding-ada-002", input=page)
            embedding = response["data"][0]["embedding"]
            embeddings.append(embedding)
        except Exception as e:
            st.error(f"Error computing embedding for a page: {e}")
            embeddings.append([])
    return embeddings

def cosine_similarity(a: List[float], b: List[float]) -> float:
    """
    Compute the cosine similarity between two vectors.
    """
    a = np.array(a)
    b = np.array(b)
    if np.linalg.norm(a) == 0 or np.linalg.norm(b) == 0:
        return 0.0
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

# ------------------------------
# Real-Time Collaboration: WebSocket Client
# ------------------------------

WS_SERVER_URL = "ws://localhost:6789"

def on_message(ws, message):
    """Callback when a message is received from the WebSocket server."""
    try:
        data = json.loads(message)
        # Append the received annotation or chat message to the shared session state list.
        if data.get("type") == "annotation":
            if "collab_annotations" not in st.session_state:
                st.session_state.collab_annotations = []
            st.session_state.collab_annotations.append(data)
        elif data.get("type") == "chat":
            if "collab_chat" not in st.session_state:
                st.session_state.collab_chat = []
            st.session_state.collab_chat.append(data)
        st.rerun()  # Use st.rerun to update the UI
    except Exception as e:
        st.error(f"Error processing collaborative message: {e}")

def on_error(ws, error):
    st.error(f"WebSocket error: {error}")

def on_close(ws, close_status_code, close_msg):
    st.info("WebSocket connection closed.")

def websocket_listen():
    """Background thread function to connect and listen to the WebSocket server."""
    ws = websocket.WebSocketApp(WS_SERVER_URL,
                                on_message=on_message,
                                on_error=on_error,
                                on_close=on_close)
    ws.run_forever()

def start_ws_client():
    """Start the WebSocket client thread if not already started."""
    if "ws_client_started" not in st.session_state:
        st.session_state.ws_client_started = True
        threading.Thread(target=websocket_listen, daemon=True).start()

# ------------------------------
# Streamlit UI Configuration
# ------------------------------

st.set_page_config(
    page_title="PDF Bot - Your AI Assistant",
    page_icon="📄",
    layout="wide",
)

# ------------------------------
# Sidebar: User Profile, Theme Selection, and File Upload
# ------------------------------

with st.sidebar:
    st.header("📂 Document Operations")
    # User Authentication / Profile
    st.subheader("User Profile")
    if "username" not in st.session_state:
        st.session_state.username = ""
    if st.session_state.username == "":
        username_input = st.text_input("Enter your username", key="username_input")
        if st.button("Set Username"):
            if username_input.strip():
                st.session_state.username = username_input.strip()
                st.success(f"Username set to '{st.session_state.username}'")
            else:
                st.error("Please enter a valid username.")
    else:
        st.info(f"Logged in as: **{st.session_state.username}**")
    
    # Theme Selection Feature
    themes = {
        "Light": {
            "background_color": "#f8f9fa",
            "text_color": "#000000",
            "header_color": "#2c3e50",
            "button_bg": "#4CAF50",
            "button_hover": "#45a049"
        },
        "Dark": {
            "background_color": "#1a1a1a",
            "text_color": "#ffffff",
            "header_color": "#ecf0f1",
            "button_bg": "#4CAF50",
            "button_hover": "#45a049"
        },
        "Ocean": {
            "background_color": "#e0f7fa",
            "text_color": "#006064",
            "header_color": "#00838f",
            "button_bg": "#00acc1",
            "button_hover": "#00838f"
        },
        "Forest": {
            "background_color": "#e8f5e9",
            "text_color": "#1b5e20",
            "header_color": "#2e7d32",
            "button_bg": "#43a047",
            "button_hover": "#388e3c"
        },
    }
    theme_choice = st.selectbox("Select Theme", list(themes.keys()), index=0)
    selected_theme = themes[theme_choice]
    background_color = selected_theme["background_color"]
    text_color = selected_theme["text_color"]
    header_color = selected_theme["header_color"]
    button_bg = selected_theme["button_bg"]
    button_hover = selected_theme["button_hover"]
    
    uploaded_file = st.file_uploader(
        "Upload your PDF",
        type=["pdf"],
        help="Maximum file size: 50MB"
    )

# ------------------------------
# Conditional CSS Styling using the Selected Theme
# ------------------------------

custom_css = f"""
    <style>
        .main {{
            background-color: {background_color};
            color: {text_color};
            padding: 2rem;
        }}
        [data-testid="stMarkdownContainer"] * {{
            color: {text_color} !important;
        }}
        textarea {{
            color: {text_color} !important;
            background-color: {background_color} !important;
            border: 1px solid #ccc !important;
        }}
        .stButton>button {{
            background-color: {button_bg};
            color: white;
            border-radius: 8px;
            padding: 12px 24px;
            transition: transform 0.2s;
        }}
        .stButton>button:hover {{
            transform: scale(1.05);
            background-color: {button_hover};
        }}
        .stDownloadButton>button {{
            background-color: #008CBA !important;
        }}
        .highlight {{
            background-color: #ffff00;
            padding: 2px 4px;
            border-radius: 4px;
        }}
        /* Header styling */
        .header {{
            text-align: center;
            padding: 2rem 0;
        }}
    </style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

# ------------------------------
# Header Section
# ------------------------------

st.markdown(f"""
    <div class="header">
        <h1 style="color: {header_color};">📄 PDF Bot</h1>
        <h3 style="color: #3498db;">Your Intelligent Document Assistant</h3>
    </div>
""", unsafe_allow_html=True)

# Start the WebSocket client for real-time collaboration if a file is uploaded
if uploaded_file:
    start_ws_client()

# ------------------------------
# Main Application Logic (with additional tabs for various functionalities)
# ------------------------------

if uploaded_file:
    with st.spinner("Processing document..."):
        start_time = time.time()
        pdf_pages, success = extract_pdf_text(uploaded_file)
        processing_time = time.time() - start_time

    if not success:
        st.stop()

    st.success(f"Document processed in {processing_time:.2f} seconds.")

    # Create tabs including the new Quiz Generation tab
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "📄 Document Text", 
        "🔍 Advanced Search", 
        "🌍 Translation & TTS", 
        "🤖 AI Summarization",
        "💬 Collaboration Chat",
        "🤖 Q&A",
        "📝 Quiz Generation"
    ])

    # --- Tab 1: Document Text Viewer with Annotations and Revision History ---
    with tab1:
        st.subheader("Document Content Viewer")
        
        # Initialize current page, annotations, revision history, and collaborative annotations in session state
        if "current_page" not in st.session_state:
            st.session_state.current_page = 0
        if "annotations" not in st.session_state:
            st.session_state.annotations = {}  # Local annotations: {page index: list of annotation dicts}
        if "revision_history" not in st.session_state:
            st.session_state.revision_history = {}  # {annotation_id: [list of revisions]}
        if "collab_annotations" not in st.session_state:
            st.session_state.collab_annotations = []  # Collaborative annotations from other users

        # Navigation Buttons
        nav_cols = st.columns([1, 2, 1])
        with nav_cols[0]:
            if st.button("Previous Page"):
                if st.session_state.current_page > 0:
                    st.session_state.current_page -= 1
        with nav_cols[1]:
            st.markdown(f"**Page {st.session_state.current_page + 1} of {len(pdf_pages)}**")
        with nav_cols[2]:
            if st.button("Next Page"):
                if st.session_state.current_page < len(pdf_pages) - 1:
                    st.session_state.current_page += 1

        # Display the current page text (non-editable)
        page_text = pdf_pages[st.session_state.current_page]

        st.text_area("Page Text (copy any part to annotate)", value=page_text, height=400,
                     key=f"page_text_{st.session_state.current_page}", disabled=True)    

        st.subheader("🎤 Press Text-to-Speech ")

        if st.button("Generate Speech"):
            if page_text.strip():
                audio_path = text_to_speech(page_text)
                
                # Play the generated audio
                with open(audio_path, "rb") as f:
                    audio_bytes = f.read()
                st.audio(audio_bytes, format="audio/mp3")
                
                st.success("✅ Speech generated successfully!")
            else:
                st.warning("⚠️ Please enter text before generating speech.")

        st.markdown("### Annotate Selected Text")
        st.markdown("*Tip: To annotate a snippet, select the text from the above area, copy it, and paste it below.*")
        selected_text = st.text_input("Enter the text you want to annotate:", key="selected_text")
        annotation_text = st.text_area("Enter your annotation for the selected text:", key="annotation_text", height=100)
        if st.button("Save Annotation"):
            if selected_text.strip() != "" and annotation_text.strip() != "":
                page_index = st.session_state.current_page
                # Create an annotation object with an ID and timestamp
                annotation_data = {
                    "id": f"{page_index}_{time.time()}",
                    "page": page_index + 1,
                    "selected_text": selected_text,
                    "annotation": annotation_text,
                    "timestamp": time.time(),
                    "user": st.session_state.username,
                    "type": "annotation"
                }
                # Save locally
                if page_index not in st.session_state.annotations:
                    st.session_state.annotations[page_index] = []
                st.session_state.annotations[page_index].append(annotation_data)
                st.success("Annotation saved locally!")
                
                # Record revision history (initial revision)
                st.session_state.revision_history[annotation_data["id"]] = [annotation_data.copy()]
                
                # Send the annotation to the WebSocket server for collaboration
                try:
                    ws = websocket.create_connection(WS_SERVER_URL)
                    ws.send(json.dumps(annotation_data))
                    ws.close()
                except Exception as e:
                    st.error(f"Failed to send annotation to collaboration server: {e}")
            else:
                st.warning("Please enter both the selected text and your annotation.")

        # Show local annotations for the current page (if any)
        page_index = st.session_state.current_page
        if page_index in st.session_state.annotations and st.session_state.annotations[page_index]:
            st.markdown("#### Your Annotations for this Page:")
            for ann in st.session_state.annotations[page_index]:
                st.markdown(f"**Annotation by {ann['user']} on Page {ann['page']}:**")
                st.markdown(f"- **Selected Text:** {ann['selected_text']}")
                st.markdown(f"- **Annotation:** {ann['annotation']}")
                # Display revision history for this annotation
                if ann["id"] in st.session_state.revision_history:
                    revs = st.session_state.revision_history[ann["id"]]
                    st.markdown("  *Revision History:*")
                    for idx, rev in enumerate(revs):
                        rev_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(rev["timestamp"]))
                        st.markdown(f"    - Revision {idx+1} at {rev_time}: {rev['annotation']}")
        else:
            st.info("No local annotations for this page yet.")

        # Display Collaborative Annotations received from other users
        st.markdown("### Collaborative Annotations from Other Users")
        if st.session_state.collab_annotations:
            for ann in st.session_state.collab_annotations:
                st.markdown(f"**From {ann.get('user', 'Unknown')} on Page {ann.get('page')}:**")
                st.markdown(f"- **Selected Text:** {ann.get('selected_text')}")
                st.markdown(f"- **Annotation:** {ann.get('annotation')}")
        else:
            st.info("No collaborative annotations received yet.")

    # --- Tab 2: Document Search Engine & Annotation (with Semantic Search) ---
    with tab2:
        st.subheader("Document Search Engine")
        # NEW: Toggle for Semantic Search
        use_semantic_search = st.checkbox("Enable Semantic Search", value=False)
        search_term = st.text_input("Enter search query:", "")
        if search_term.strip():
            if use_semantic_search:
                # Compute and cache embeddings if not already done
                if "page_embeddings" not in st.session_state:
                    with st.spinner("Computing embeddings for document pages..."):
                        st.session_state.page_embeddings = compute_page_embeddings(pdf_pages)
                with st.spinner("Performing semantic search..."):
                    try:
                        response = openai.Embedding.create(model="text-embedding-ada-002", input=search_term)
                        query_embedding = response["data"][0]["embedding"]
                        results = []
                        for i, page_embedding in enumerate(st.session_state.page_embeddings):
                            if page_embedding:
                                score = cosine_similarity(query_embedding, page_embedding)
                                results.append((i+1, score, pdf_pages[i]))
                        results.sort(key=lambda x: x[1], reverse=True)
                        top_results = results[:3]  # Show top 3 matches
                        if top_results:
                            st.success(f"Top {len(top_results)} semantic match(es):")
                            for page, score, text in top_results:
                                snippet = text[:200] + "..." if len(text) > 200 else text
                                st.markdown(f"**Page {page} (Score: {score:.2f}):** {snippet}")
                        else:
                            st.warning("No semantic matches found.")
                    except Exception as e:
                        st.error(f"Semantic search error: {e}")
            else:
                # Keyword-based search (existing functionality)
                matches = []
                pattern = re.compile(re.escape(search_term), re.IGNORECASE)
                for page_num, text in enumerate(pdf_pages):
                    for match in pattern.finditer(text):
                        # Extract context around the match (up to 100 characters on either side)
                        start_context = max(0, match.start() - 100)
                        end_context = min(len(text), match.end() + 100)
                        context = text[start_context:end_context]
                        # Highlight the match within the context
                        highlighted = pattern.sub(r'<span class="highlight">\g<0></span>', context)
                        matches.append((page_num + 1, highlighted))
                
                if matches:
                    st.success(f"Found {len(matches)} match(es):")
                    # Loop through each match and allow annotation
                    for idx, (page, context) in enumerate(matches):
                        with st.container():
                            st.markdown(f"**Page {page}:** {context}", unsafe_allow_html=True)
                            annotate_toggle = st.checkbox("Add Annotation", key=f"annotate_toggle_{idx}")
                            if annotate_toggle:
                                if f"annotation_{idx}" not in st.session_state:
                                    st.session_state[f"annotation_{idx}"] = ""
                                annotation = st.text_area("Enter your annotation:", 
                                                          value=st.session_state[f"annotation_{idx}"], 
                                                          key=f"annotation_{idx}_area")
                                st.session_state[f"annotation_{idx}"] = annotation
                                if annotation:
                                    st.info(f"Annotation: {annotation}")
                else:
                    st.warning("No matches found in the document.")

    # --- Tab 3: Translation & Text-to-Speech ---
    with tab3:
        st.subheader("Translation & Text-to-Speech")
        col1, col2 = st.columns(2)

        # Text Translation Section
        with col1:
            st.markdown("### Text Translation")
            target_lang = st.selectbox(
                "Target Language:",
                ["es", "fr", "de", "zh-cn", "ja", "ru"],
                index=0
            )
            text_to_translate = st.text_area("Enter text to translate:", height=150)
            if st.button("Translate Text"):
                if text_to_translate.strip():
                    with st.spinner("Translating..."):
                        result = translate_text(text_to_translate, target_lang)
                    st.success("Translation Result:")
                    st.write(result)
                else:
                    st.warning("Please enter text to translate.")

        # Text-to-Speech Section
        with col2:
            st.subheader("🎤 Press Text-to-Speech ")
            tts_text = st.text_area("Enter text to speak:", height=150)
            if st.button("Generate Speech", key=456):
                if tts_text.strip():
                    audio_path = text_to_speech(tts_text)
                    
                    # Play the generated audio
                    with open(audio_path, "rb") as f:
                        audio_bytes = f.read()
                    st.audio(audio_bytes, format="audio/mp3")
                    
                    st.success("✅ Speech generated successfully!")
                else:
                    st.warning("⚠️ Please enter text before generating speech.")

    # --- Tab 4: AI-Powered Summarization ---
    with tab4:
        st.subheader("AI-Powered Summarization")
        st.markdown("Use the OpenAI API to generate a concise summary of your document content.")

        # Option to select between summarizing the entire document or a single page.
        summary_option = st.radio("Summarize:", ("Entire Document", "Current Page"), index=1)
        if summary_option == "Entire Document":
            # Concatenate all pages (you might want to limit the length if the PDF is very large)
            full_text = "\n".join(pdf_pages)
            if st.button("Summarize Entire Document"):
                with st.spinner("Summarizing entire document..."):
                    summary = summarize_text(full_text)
                st.markdown("#### Summary:")
                st.write(summary)
        else:
            # Summarize only the current page
            current_text = pdf_pages[st.session_state.current_page]
            st.markdown(f"**Current Page ({st.session_state.current_page + 1}) Content:**")
            st.text_area("Page Text", value=current_text, height=200, disabled=True)
            if st.button("Summarize Current Page"):
                with st.spinner("Summarizing current page..."):
                    summary = summarize_text(current_text)
                st.markdown("#### Summary:")
                st.write(summary)

    # --- Tab 5: Collaboration Chat ---
    with tab5:
        st.subheader("Collaboration Chat")
        st.markdown("Discuss the document with other users in real-time.")
        
        # Initialize chat history in session state if needed
        if "collab_chat" not in st.session_state:
            st.session_state.collab_chat = []
        
        # Display chat history
        st.markdown("### Chat History:")
        if st.session_state.collab_chat:
            for msg in st.session_state.collab_chat:
                msg_time = time.strftime("%H:%M:%S", time.localtime(msg.get("timestamp", time.time())))
                st.markdown(f"**{msg.get('user', 'Anonymous')}** at {msg_time}: {msg.get('message')}")
        else:
            st.info("No chat messages yet.")
        
        # Chat message input
        chat_message = st.text_input("Enter your message:", key="chat_message_input")
        if st.button("Send Message"):
            if chat_message.strip():
                chat_data = {
                    "type": "chat",
                    "timestamp": time.time(),
                    "user": st.session_state.username,
                    "message": chat_message.strip()
                }
                # Append to local chat history
                st.session_state.collab_chat.append(chat_data)
                # Send the chat message to the WebSocket server
                try:
                    ws = websocket.create_connection(WS_SERVER_URL)
                    ws.send(json.dumps(chat_data))
                    ws.close()
                except Exception as e:
                    st.error(f"Failed to send chat message to collaboration server: {e}")
                st.rerun()  # Update the UI
            else:
                st.warning("Please enter a message.")

    # --- Tab 6: Q&A Interface ---
    with tab6:
        st.subheader("Question Answering")
        st.markdown("Ask a question about the document and receive an answer along with citations to relevant pages.")
        question = st.text_input("Enter your question:", key="qa_question")
        if st.button("Get Answer"):
            if question.strip():
                with st.spinner("Processing question..."):
                    answer, relevant_pages = answer_question(question, pdf_pages)
                st.markdown("#### Answer:")
                st.write(answer)
                if relevant_pages:
                    st.markdown("#### Relevant Pages:")
                    st.write(", ".join(map(str, relevant_pages)))
                else:
                    st.info("No relevant pages found.")
            else:
                st.warning("Please enter a question.")

    # --- Tab 7: Quiz Generation ---
    with tab7:
        st.subheader("Quiz Generation")
        st.markdown("Generate quiz questions (with answers) based on your document.")
        quiz_option = st.radio("Generate quiz from:", ("Entire Document", "Current Page"), index=0)
        num_questions = st.number_input("Number of Questions:", min_value=1, max_value=20, value=5)
        if st.button("Generate Quiz"):
            with st.spinner("Generating quiz..."):
                if quiz_option == "Entire Document":
                    text_for_quiz = "\n".join(pdf_pages)
                else:
                    text_for_quiz = pdf_pages[st.session_state.current_page]
                quiz = generate_quiz(text_for_quiz, num_questions=num_questions)
            st.markdown("#### Quiz:")
            st.write(quiz)

# ------------------------------
# Footer Section
# ------------------------------

st.markdown(f"""
    <div style="text-align: center; padding: 2rem 0; color: {text_color};">
        <hr style="margin: 1rem 0;">
        <p>PDF Bot v1.0 • Secure Document Processing</p>
    </div>
""", unsafe_allow_html=True)
