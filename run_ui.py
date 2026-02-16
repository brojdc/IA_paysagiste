import os
import sys

if __name__ == "__main__":
    os.system(f'"{sys.executable}" -m streamlit run ui/formulaire.py --server.port 8502')
