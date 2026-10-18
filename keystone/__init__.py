try:  # local convenience: read .env if present (python-dotenv ships with mcp)
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass
