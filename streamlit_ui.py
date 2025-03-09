from __future__ import annotations
from supabase import Client, create_client
from typing import Literal, TypedDict
from urllib.parse import urlparse
from openai import AsyncOpenAI
from dotenv import load_dotenv
import streamlit as st
import subprocess
import importlib
import threading
import platform
import logfire
import asyncio
import queue
import time
import json
import sys
import os

# Set page config - must be the first Streamlit command
st.set_page_config(
    page_title="Archon - Agent Builder",
    page_icon="🤖",
    layout="wide",
)

from utils.utils import get_env_var, save_env_var, write_to_log, create_new_tab_button
from streamlit_pages.styles import load_css
from streamlit_pages.intro import intro_tab
from streamlit_pages.chat import chat_tab
from streamlit_pages.mcp import mcp_tab
from streamlit_pages.future_enhancements import future_enhancements_tab

# Load environment variables from .env file
load_dotenv()

# Initialize clients
openai_client = None
base_url = get_env_var('BASE_URL') or 'https://api.openai.com/v1'
api_key = get_env_var('LLM_API_KEY') or 'no-llm-api-key-provided'
is_ollama = "localhost" in base_url.lower()

if is_ollama:
    openai_client = AsyncOpenAI(base_url=base_url,api_key=api_key)
elif get_env_var("OPENAI_API_KEY"):
    openai_client = AsyncOpenAI(api_key=get_env_var("OPENAI_API_KEY"))
else:
    openai_client = None

if get_env_var("SUPABASE_URL"):
    supabase: Client = Client(
            get_env_var("SUPABASE_URL"),
            get_env_var("SUPABASE_SERVICE_KEY")
        )
else:
    supabase = None

# Load custom CSS styles
load_css()

# Function to reload the archon_graph module
def reload_archon_graph():
    """Reload the archon_graph module to apply new environment variables"""
    try:
        # First reload pydantic_ai_coder
        import archon.pydantic_ai_coder
        importlib.reload(archon.pydantic_ai_coder)
        
        # Then reload archon_graph which imports pydantic_ai_coder
        import archon.archon_graph
        importlib.reload(archon.archon_graph)
        
        st.success("Successfully reloaded Archon modules with new environment variables!")
        return True
    except Exception as e:
        st.error(f"Error reloading Archon modules: {str(e)}")
        return False
    
# Configure logfire to suppress warnings (optional)
logfire.configure(send_to_logfire='never')

def documentation_tab():
    """Display the documentation interface"""
    st.header("Documentation")
    
    # Create tabs for different documentation sources
    doc_tabs = st.tabs(["Pydantic AI Docs", "Future Sources"])
    
    with doc_tabs[0]:
        st.subheader("Pydantic AI Documentation")
        st.markdown("""
        This section allows you to crawl and index the Pydantic AI documentation.
        The crawler will:
        
        1. Fetch URLs from the Pydantic AI sitemap
        2. Crawl each page and extract content
        3. Split content into chunks
        4. Generate embeddings for each chunk
        5. Store the chunks in the Supabase database
        
        This process may take several minutes depending on the number of pages.
        """)
        
        # Check if the database is configured
        supabase_url = get_env_var("SUPABASE_URL")
        supabase_key = get_env_var("SUPABASE_SERVICE_KEY")
        
        if not supabase_url or not supabase_key:
            st.warning("⚠️ Supabase is not configured. Please set up your environment variables first.")
            create_new_tab_button("Go to Environment Section", "Environment", key="goto_env_from_docs")
        else:
            # Initialize session state for tracking crawl progress
            if "crawl_tracker" not in st.session_state:
                st.session_state.crawl_tracker = None
            
            if "crawl_status" not in st.session_state:
                st.session_state.crawl_status = None
                
            if "last_update_time" not in st.session_state:
                st.session_state.last_update_time = time.time()
            
            # Create columns for the buttons
            col1, col2 = st.columns(2)
            
            with col1:
                # Button to start crawling
                if st.button("Crawl Pydantic AI Docs", key="crawl_pydantic") and not (st.session_state.crawl_tracker and st.session_state.crawl_tracker.is_running):
                    try:
                        # Import the progress tracker
                        from archon.crawl_pydantic_ai_docs import start_crawl_with_requests
                        
                        # Define a callback function to update the session state
                        def update_progress(status):
                            st.session_state.crawl_status = status
                        
                        # Start the crawling process in a separate thread
                        st.session_state.crawl_tracker = start_crawl_with_requests(update_progress)
                        st.session_state.crawl_status = st.session_state.crawl_tracker.get_status()
                        
                        # Force a rerun to start showing progress
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error starting crawl: {str(e)}")
            
            with col2:
                # Button to clear existing Pydantic AI docs
                if st.button("Clear Pydantic AI Docs", key="clear_pydantic"):
                    with st.spinner("Clearing existing Pydantic AI docs..."):
                        try:
                            # Import the function to clear records
                            from archon.crawl_pydantic_ai_docs import clear_existing_records
                            
                            # Run the function to clear records
                            asyncio.run(clear_existing_records())
                            st.success("✅ Successfully cleared existing Pydantic AI docs from the database.")
                            
                            # Force a rerun to update the UI
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Error clearing Pydantic AI docs: {str(e)}")
            
            # Display crawling progress if a crawl is in progress or has completed
            if st.session_state.crawl_tracker:
                # Create a container for the progress information
                progress_container = st.container()
                
                with progress_container:
                    # Get the latest status
                    current_time = time.time()
                    # Update status every second
                    if current_time - st.session_state.last_update_time >= 1:
                        st.session_state.crawl_status = st.session_state.crawl_tracker.get_status()
                        st.session_state.last_update_time = current_time
                    
                    status = st.session_state.crawl_status
                    
                    # Display a progress bar
                    if status and status["urls_found"] > 0:
                        progress = status["urls_processed"] / status["urls_found"]
                        st.progress(progress)
                    
                    # Display status metrics
                    col1, col2, col3, col4 = st.columns(4)
                    if status:
                        col1.metric("URLs Found", status["urls_found"])
                        col2.metric("URLs Processed", status["urls_processed"])
                        col3.metric("Successful", status["urls_succeeded"])
                        col4.metric("Failed", status["urls_failed"])
                    else:
                        col1.metric("URLs Found", 0)
                        col2.metric("URLs Processed", 0)
                        col3.metric("Successful", 0)
                        col4.metric("Failed", 0)
                    
                    # Display logs in an expander
                    with st.expander("Crawling Logs", expanded=True):
                        if status and "logs" in status:
                            logs_text = "\n".join(status["logs"][-20:])  # Show last 20 logs
                            st.code(logs_text)
                        else:
                            st.code("No logs available yet...")
                    
                    # Show completion message
                    if status and not status["is_running"] and status["end_time"]:
                        if status["urls_failed"] == 0:
                            st.success("✅ Crawling process completed successfully!")
                        else:
                            st.warning(f"⚠️ Crawling process completed with {status['urls_failed']} failed URLs.")
                
                # Auto-refresh while crawling is in progress
                if not status or status["is_running"]:
                    st.rerun()
        
        # Display database statistics
        st.subheader("Database Statistics")
        try:
            # Connect to Supabase
            from supabase import create_client
            supabase_client = create_client(supabase_url, supabase_key)
            
            # Query the count of Pydantic AI docs
            result = supabase_client.table("site_pages").select("count", count="exact").eq("metadata->>source", "pydantic_ai_docs").execute()
            count = result.count if hasattr(result, "count") else 0
            
            # Display the count
            st.metric("Pydantic AI Docs Chunks", count)
            
            # Add a button to view the data
            if count > 0 and st.button("View Indexed Data", key="view_pydantic_data"):
                # Query a sample of the data
                sample_data = supabase_client.table("site_pages").select("url,title,summary,chunk_number").eq("metadata->>source", "pydantic_ai_docs").limit(10).execute()
                
                # Display the sample data
                st.dataframe(sample_data.data)
                st.info("Showing up to 10 sample records. The database contains more records.")
        except Exception as e:
            st.error(f"Error querying database: {str(e)}")
    
    with doc_tabs[1]:
        st.info("Additional documentation sources will be available in future updates.")

@st.cache_data
def load_sql_template():
    """Load the SQL template file and cache it"""
    with open(os.path.join(os.path.dirname(__file__), "utils", "site_pages.sql"), "r") as f:
        return f.read()

def database_tab():
    """Display the database configuration interface"""
    st.header("Database Configuration")
    st.write("Set up and manage your Supabase database tables for Archon.")
    
    # Check if Supabase is configured
    if not supabase:
        st.error("Supabase is not configured. Please set your Supabase URL and Service Key in the Environment tab.")
        return
    
    # Site Pages Table Setup
    st.subheader("Site Pages Table")
    st.write("This table stores web page content and embeddings for semantic search.")
    
    # Add information about the table
    with st.expander("About the Site Pages Table", expanded=False):
        st.markdown("""
        This table is used to store:
        - Web page content split into chunks
        - Vector embeddings for semantic search
        - Metadata for filtering results
        
        The table includes:
        - URL and chunk number (unique together)
        - Title and summary of the content
        - Full text content
        - Vector embeddings for similarity search
        - Metadata in JSON format
        
        It also creates:
        - A vector similarity search function
        - Appropriate indexes for performance
        - Row-level security policies for Supabase
        """)
    
    # Check if the table already exists
    table_exists = False
    table_has_data = False
    
    try:
        # Try to query the table to see if it exists
        response = supabase.table("site_pages").select("id").limit(1).execute()
        table_exists = True
        
        # Check if the table has data
        count_response = supabase.table("site_pages").select("*", count="exact").execute()
        row_count = count_response.count if hasattr(count_response, 'count') else 0
        table_has_data = row_count > 0
        
        st.success("✅ The site_pages table already exists in your database.")
        if table_has_data:
            st.info(f"The table contains data ({row_count} rows).")
        else:
            st.info("The table exists but contains no data.")
    except Exception as e:
        error_str = str(e)
        if "relation" in error_str and "does not exist" in error_str:
            st.info("The site_pages table does not exist yet. You can create it below.")
        else:
            st.error(f"Error checking table status: {error_str}")
            st.info("Proceeding with the assumption that the table needs to be created.")
        table_exists = False
    
    # Vector dimensions selection
    st.write("### Vector Dimensions")
    st.write("Select the embedding dimensions based on your embedding model:")
    
    vector_dim = st.selectbox(
        "Embedding Dimensions",
        options=[1536, 768, 384, 1024],
        index=0,
        help="Use 1536 for OpenAI embeddings, 768 for nomic-embed-text with Ollama, or select another dimension based on your model."
    )
    
    # Get the SQL with the selected vector dimensions
    sql_template = load_sql_template()
    
    # Replace the vector dimensions in the SQL
    sql = sql_template.replace("vector(1536)", f"vector({vector_dim})")
    
    # Also update the match_site_pages function dimensions
    sql = sql.replace("query_embedding vector(1536)", f"query_embedding vector({vector_dim})")
    
    # Show the SQL
    with st.expander("View SQL", expanded=False):
        st.code(sql, language="sql")
    
    # Create table button
    if not table_exists:
        if st.button("Get Instructions for Creating Site Pages Table"):
            show_manual_sql_instructions(sql)
    else:
        # Option to recreate the table or clear data
        col1, col2 = st.columns(2)
        
        with col1:
            st.warning("⚠️ Recreating will delete all existing data.")
            if st.button("Get Instructions for Recreating Site Pages Table"):
                show_manual_sql_instructions(sql, recreate=True)
        
        with col2:
            if table_has_data:
                st.warning("⚠️ Clear all data but keep structure.")
                if st.button("Clear Table Data"):
                    try:
                        with st.spinner("Clearing table data..."):
                            # Use the Supabase client to delete all rows
                            response = supabase.table("site_pages").delete().neq("id", 0).execute()
                            st.success("✅ Table data cleared successfully!")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Error clearing table data: {str(e)}")
                        # Fall back to manual SQL
                        truncate_sql = "TRUNCATE TABLE site_pages;"
                        st.code(truncate_sql, language="sql")
                        st.info("Execute this SQL in your Supabase SQL Editor to clear the table data.")
                        
                        # Provide a link to the Supabase SQL Editor
                        supabase_url = get_env_var("SUPABASE_URL")
                        if supabase_url:
                            dashboard_url = get_supabase_sql_editor_url(supabase_url)
                            st.markdown(f"[Open Your Supabase SQL Editor with this URL]({dashboard_url})")
                    
def get_supabase_sql_editor_url(supabase_url):
    """Get the URL for the Supabase SQL Editor"""
    try:
        # Extract the project reference from the URL
        # Format is typically: https://<project-ref>.supabase.co
        if '//' in supabase_url:
            parts = supabase_url.split('//')
            if len(parts) > 1:
                domain_parts = parts[1].split('.')
                if len(domain_parts) > 0:
                    project_ref = domain_parts[0]
                    return f"https://supabase.com/dashboard/project/{project_ref}/sql/new"
        
        # Fallback to a generic URL
        return "https://supabase.com/dashboard"
    except Exception:
        return "https://supabase.com/dashboard"

def show_manual_sql_instructions(sql, recreate=False):
    """Show instructions for manually executing SQL in Supabase"""
    st.info("### Manual SQL Execution Instructions")
    
    # Provide a link to the Supabase SQL Editor
    supabase_url = get_env_var("SUPABASE_URL")
    if supabase_url:
        dashboard_url = get_supabase_sql_editor_url(supabase_url)
        st.markdown(f"**Step 1:** [Open Your Supabase SQL Editor with this URL]({dashboard_url})")
    else:
        st.markdown("**Step 1:** Open your Supabase Dashboard and navigate to the SQL Editor")
    
    st.markdown("**Step 2:** Create a new SQL query")
    
    if recreate:
        st.markdown("**Step 3:** Copy and execute the following SQL:")
        drop_sql = "DROP TABLE IF EXISTS site_pages CASCADE;"
        st.code(drop_sql, language="sql")
        
        st.markdown("**Step 4:** Then copy and execute this SQL:")
        st.code(sql, language="sql")
    else:
        st.markdown("**Step 3:** Copy and execute the following SQL:")
        st.code(sql, language="sql")
    
    st.success("After executing the SQL, return to this page and refresh to see the updated table status.")

def agent_service_tab():
    """Display the agent service interface for managing the graph service"""
    st.header("MCP Agent Service")
    st.write("Start, restart, and monitor the Archon agent service for MCP.")
    
    # Initialize session state variables if they don't exist
    if "service_process" not in st.session_state:
        st.session_state.service_process = None
    if "service_running" not in st.session_state:
        st.session_state.service_running = False
    if "service_output" not in st.session_state:
        st.session_state.service_output = []
    if "output_queue" not in st.session_state:
        st.session_state.output_queue = queue.Queue()
    
    # Function to check if the service is running
    def is_service_running():
        if st.session_state.service_process is None:
            return False
        
        # Check if process is still running
        return st.session_state.service_process.poll() is None
    
    # Function to kill any process using port 8100
    def kill_process_on_port(port):
        try:
            if platform.system() == "Windows":
                # Windows: use netstat to find the process using the port
                result = subprocess.run(
                    f'netstat -ano | findstr :{port}',
                    shell=True, 
                    capture_output=True, 
                    text=True
                )
                
                if result.stdout:
                    # Extract the PID from the output
                    for line in result.stdout.splitlines():
                        if f":{port}" in line and "LISTENING" in line:
                            parts = line.strip().split()
                            pid = parts[-1]
                            # Kill the process
                            subprocess.run(f'taskkill /F /PID {pid}', shell=True)
                            st.session_state.output_queue.put(f"[{time.strftime('%H:%M:%S')}] Killed any existing process using port {port} (PID: {pid})\n")
                            return True
            else:
                # Unix-like systems: use lsof to find the process using the port
                result = subprocess.run(
                    f'lsof -i :{port} -t',
                    shell=True, 
                    capture_output=True, 
                    text=True
                )
                
                if result.stdout:
                    # Extract the PID from the output
                    pid = result.stdout.strip()
                    # Kill the process
                    subprocess.run(f'kill -9 {pid}', shell=True)
                    st.session_state.output_queue.put(f"[{time.strftime('%H:%M:%S')}] Killed process using port {port} (PID: {pid})\n")
                    return True
                    
            return False
        except Exception as e:
            st.session_state.output_queue.put(f"[{time.strftime('%H:%M:%S')}] Error killing process on port {port}: {str(e)}\n")
            return False
    
    # Update service status
    st.session_state.service_running = is_service_running()
    
    # Process any new output in the queue
    try:
        while not st.session_state.output_queue.empty():
            line = st.session_state.output_queue.get_nowait()
            if line:
                st.session_state.service_output.append(line)
    except Exception:
        pass
    
    # Create button text based on service status
    button_text = "Restart Agent Service" if st.session_state.service_running else "Start Agent Service"
    
    # Create columns for buttons
    col1, col2 = st.columns([1, 1])
    
    # Start/Restart button
    with col1:
        if st.button(button_text, use_container_width=True):
            # Stop existing process if running
            if st.session_state.service_running:
                try:
                    st.session_state.service_process.terminate()
                    time.sleep(1)  # Give it time to terminate
                    if st.session_state.service_process.poll() is None:
                        # Force kill if still running
                        st.session_state.service_process.kill()
                except Exception as e:
                    st.error(f"Error stopping service: {str(e)}")
            
            # Clear previous output
            st.session_state.service_output = []
            st.session_state.output_queue = queue.Queue()
            
            # Kill any process using port 8100
            kill_process_on_port(8100)
            
            # Start new process
            try:
                # Get the absolute path to the graph service script
                base_path = os.path.abspath(os.path.dirname(__file__))
                graph_service_path = os.path.join(base_path, 'graph_service.py')
                
                # Start the process with output redirection
                process = subprocess.Popen(
                    [sys.executable, graph_service_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    universal_newlines=True
                )
                
                st.session_state.service_process = process
                st.session_state.service_running = True
                
                # Start threads to read output
                def read_output(stream, queue_obj):
                    for line in iter(stream.readline, ''):
                        queue_obj.put(line)
                    stream.close()
                
                # Start threads for stdout and stderr
                threading.Thread(target=read_output, args=(process.stdout, st.session_state.output_queue), daemon=True).start()
                threading.Thread(target=read_output, args=(process.stderr, st.session_state.output_queue), daemon=True).start()
                
                # Add startup message
                st.session_state.output_queue.put(f"[{time.strftime('%H:%M:%S')}] Agent service started\n")
                
                st.success("Agent service started successfully!")
                st.rerun()
                
            except Exception as e:
                st.error(f"Error starting service: {str(e)}")
                st.session_state.output_queue.put(f"[{time.strftime('%H:%M:%S')}] Error: {str(e)}\n")
    
    # Stop button
    with col2:
        stop_button = st.button("Stop Agent Service", disabled=not st.session_state.service_running, use_container_width=True)
        if stop_button and st.session_state.service_running:
            try:
                st.session_state.service_process.terminate()
                time.sleep(1)  # Give it time to terminate
                if st.session_state.service_process.poll() is None:
                    # Force kill if still running
                    st.session_state.service_process.kill()
                
                st.session_state.service_running = False
                st.session_state.output_queue.put(f"[{time.strftime('%H:%M:%S')}] Agent service stopped\n")
                st.success("Agent service stopped successfully!")
                st.rerun()
                
            except Exception as e:
                st.error(f"Error stopping service: {str(e)}")
                st.session_state.output_queue.put(f"[{time.strftime('%H:%M:%S')}] Error stopping: {str(e)}\n")
    
    # Service status indicator
    status_color = "🟢" if st.session_state.service_running else "🔴"
    status_text = "Running" if st.session_state.service_running else "Stopped"
    st.write(f"**Service Status:** {status_color} {status_text}")
    
    # Add auto-refresh option
    auto_refresh = st.checkbox("Auto-refresh output (uncheck this before copying any error message)", value=True)
    
    # Display output in a scrollable container
    st.subheader("Service Output")
    
    # Calculate height based on number of lines, but cap it
    output_height = min(400, max(200, len(st.session_state.service_output) * 20))
    
    # Create a scrollable container for the output
    with st.container():
        # Join all output lines and display in the container
        output_text = "".join(st.session_state.service_output)
        
        # For auto-scrolling, we'll use a different approach
        if auto_refresh and st.session_state.service_running and output_text:
            # We'll reverse the output text so the newest lines appear at the top
            # This way they're always visible without needing to scroll
            lines = output_text.splitlines()
            reversed_lines = lines[::-1]  # Reverse the lines
            output_text = "\n".join(reversed_lines)
            
            # Add a note at the top (which will appear at the bottom of the reversed text)
            note = "--- SHOWING NEWEST LOGS FIRST (AUTO-SCROLL MODE) ---\n\n"
            output_text = note + output_text
        
        # Use a text area for scrollable output
        st.text_area(
            label="Realtime Logs from Archon Service",
            value=output_text,
            height=output_height,
            disabled=True,
            key="output_text_area"  # Use a fixed key to maintain state between refreshes
        )
        
        # Add a toggle for reversed mode
        if auto_refresh and st.session_state.service_running:
            st.caption("Logs are shown newest-first for auto-scrolling. Disable auto-refresh to see logs in chronological order.")
    
    # Add a clear output button
    if st.button("Clear Output"):
        st.session_state.service_output = []
        st.rerun()
    
    # Auto-refresh if enabled and service is running
    if auto_refresh and st.session_state.service_running:
        time.sleep(0.1)  # Small delay to prevent excessive CPU usage
        st.rerun()

def environment_tab():
    """Display the environment variables configuration interface"""
    st.header("Environment Variables")
    st.write("- Configure your environment variables for Archon. These settings will be saved and used for future sessions.")
    st.write("- NOTE: Press 'enter' to save after inputting a variable, otherwise click the 'save' button at the bottom.")
    st.write("- HELP: Hover over the '?' icon on the right for each environment variable for help/examples.")
    st.warning("⚠️ If your agent service for MCP is already running, you'll need to restart it after changing environment variables.")

    # Define environment variables and their descriptions from .env.example
    env_vars = {
        "BASE_URL": {
            "description": "Base URL for the OpenAI instance (default is https://api.openai.com/v1)",
            "help": "OpenAI: https://api.openai.com/v1\n\n\n\nAnthropic: https://api.anthropic.com/v1\n\nOllama (example): http://localhost:11434/v1\n\nOpenRouter: https://openrouter.ai/api/v1",
            "sensitive": False
        },
        "LLM_API_KEY": {
            "description": "API key for your LLM provider",
            "help": "For OpenAI: https://help.openai.com/en/articles/4936850-where-do-i-find-my-openai-api-key\n\nFor Anthropic: https://console.anthropic.com/account/keys\n\nFor OpenRouter: https://openrouter.ai/keys\n\nFor Ollama, no need to set this unless you specifically configured an API key",
            "sensitive": True
        },
        "OPENAI_API_KEY": {
            "description": "Your OpenAI API key",
            "help": "Get your Open AI API Key by following these instructions -\n\nhttps://help.openai.com/en/articles/4936850-where-do-i-find-my-openai-api-key\n\nEven if using OpenRouter, you still need to set this for the embedding model.\n\nNo need to set this if using Ollama.",
            "sensitive": True
        },
        "SUPABASE_URL": {
            "description": "URL for your Supabase project",
            "help": "Get your SUPABASE_URL from the API section of your Supabase project settings -\nhttps://supabase.com/dashboard/project/<your project ID>/settings/api",
            "sensitive": False
        },
        "SUPABASE_SERVICE_KEY": {
            "description": "Service key for your Supabase project",
            "help": "Get your SUPABASE_SERVICE_KEY from the API section of your Supabase project settings -\nhttps://supabase.com/dashboard/project/<your project ID>/settings/api\nOn this page it is called the service_role secret.",
            "sensitive": True
        },
        "REASONER_MODEL": {
            "description": "The LLM you want to use for the reasoner",
            "help": "Example: o3-mini\n\nExample: deepseek-r1:7b-8k",
            "sensitive": False
        },
        "PRIMARY_MODEL": {
            "description": "The LLM you want to use for the primary agent/coder",
            "help": "Example: gpt-4o-mini\n\nExample: qwen2.5:14b-instruct-8k",
            "sensitive": False
        },
        "EMBEDDING_MODEL": {
            "description": "Embedding model you want to use",
            "help": "Example for Ollama: nomic-embed-text\n\nExample for OpenAI: text-embedding-3-small",
            "sensitive": False
        }
    }
    
    # Create a form for the environment variables
    with st.form("env_vars_form"):
        updated_values = {}
        
        # Display input fields for each environment variable
        for var_name, var_info in env_vars.items():
            current_value = get_env_var(var_name) or ""
            
            # Display the variable description
            st.subheader(var_name)
            st.write(var_info["description"])
            
            # Display input field (password field for sensitive data)
            if var_info["sensitive"]:
                # If there's already a value, show asterisks in the placeholder
                placeholder = "Set but hidden" if current_value else ""
                new_value = st.text_input(
                    f"Enter {var_name}:", 
                    type="password",
                    help=var_info["help"],
                    key=f"input_{var_name}",
                    placeholder=placeholder
                )
                # Only update if user entered something (to avoid overwriting with empty string)
                if new_value:
                    updated_values[var_name] = new_value
            else:
                new_value = st.text_input(
                    f"Enter {var_name}:", 
                    value=current_value,
                    help=var_info["help"],
                    key=f"input_{var_name}"
                )
                # Always update non-sensitive values (can be empty)
                updated_values[var_name] = new_value
            
            # Add a separator between variables
            st.markdown("---")
        
        # Submit button
        submitted = st.form_submit_button("Save Environment Variables")
        
        if submitted:
            # Save all updated values
            success = True
            for var_name, value in updated_values.items():
                if value:  # Only save non-empty values
                    if not save_env_var(var_name, value):
                        success = False
                        st.error(f"Failed to save {var_name}.")
            
            if success:
                st.success("Environment variables saved successfully!")
                reload_archon_graph()

async def main():
    # Check for tab query parameter
    query_params = st.query_params
    if "tab" in query_params:
        tab_name = query_params["tab"]
        if tab_name in ["Intro", "Chat", "Environment", "Database", "Documentation", "Agent Service", "MCP", "Future Enhancements"]:
            st.session_state.selected_tab = tab_name

    # Add sidebar navigation
    with st.sidebar:
        st.image("public/ArchonLightGrey.png", width=1000)
        
        # Navigation options with vertical buttons
        st.write("### Navigation")
        
        # Initialize session state for selected tab if not present
        if "selected_tab" not in st.session_state:
            st.session_state.selected_tab = "Intro"
        
        # Vertical navigation buttons
        intro_button = st.button("Intro", use_container_width=True, key="intro_button")
        chat_button = st.button("Chat", use_container_width=True, key="chat_button")
        env_button = st.button("Environment", use_container_width=True, key="env_button")
        db_button = st.button("Database", use_container_width=True, key="db_button")
        docs_button = st.button("Documentation", use_container_width=True, key="docs_button")
        service_button = st.button("Agent Service", use_container_width=True, key="service_button")
        mcp_button = st.button("MCP", use_container_width=True, key="mcp_button")
        future_enhancements_button = st.button("Future Enhancements", use_container_width=True, key="future_enhancements_button")
        
        # Update selected tab based on button clicks
        if intro_button:
            st.session_state.selected_tab = "Intro"
        elif chat_button:
            st.session_state.selected_tab = "Chat"
        elif mcp_button:
            st.session_state.selected_tab = "MCP"
        elif env_button:
            st.session_state.selected_tab = "Environment"
        elif service_button:
            st.session_state.selected_tab = "Agent Service"
        elif db_button:
            st.session_state.selected_tab = "Database"
        elif docs_button:
            st.session_state.selected_tab = "Documentation"
        elif future_enhancements_button:
            st.session_state.selected_tab = "Future Enhancements"
    
    # Display the selected tab
    if st.session_state.selected_tab == "Intro":
        st.title("Archon - Introduction")
        intro_tab()
    elif st.session_state.selected_tab == "Chat":
        st.title("Archon - Agent Builder")
        await chat_tab()
    elif st.session_state.selected_tab == "MCP":
        st.title("Archon - MCP Configuration")
        mcp_tab()
    elif st.session_state.selected_tab == "Environment":
        st.title("Archon - Environment Configuration")
        environment_tab()
    elif st.session_state.selected_tab == "Agent Service":
        st.title("Archon - Agent Service")
        agent_service_tab()
    elif st.session_state.selected_tab == "Database":
        st.title("Archon - Database Configuration")
        database_tab()
    elif st.session_state.selected_tab == "Documentation":
        st.title("Archon - Documentation")
        documentation_tab()
    elif st.session_state.selected_tab == "Future Enhancements":
        st.title("Archon - Future Enhancements")
        future_enhancements_tab()

if __name__ == "__main__":
    asyncio.run(main())
