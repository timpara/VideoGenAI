# If you could not download the model from the official site, you can use the mirror site.
# Just remove the comment of the following line.

# export HF_ENDPOINT=https://hf-mirror.com

streamlit run ./webui/Main.py --browser.serverAddress="0.0.0.0" --server.enableCORS=True --browser.gatherUsageStats=False
