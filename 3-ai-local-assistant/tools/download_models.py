"""
download_models.py - One-time setup: downloads JARVIS wake word model files.

Run this once from your activated venv before starting main.py:
    python download_models.py
"""
import os
import urllib.request

BASE = "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1"
MODELS = {
    "hey_jarvis_v0.1.onnx": "{}/hey_jarvis_v0.1.onnx".format(BASE),
    "melspectrogram.onnx" : "{}/melspectrogram.onnx".format(BASE),
    "embedding_model.onnx": "{}/embedding_model.onnx".format(BASE),
}

def main():
    import openwakeword
    models_dir = os.path.join(
        os.path.dirname(os.path.abspath(openwakeword.__file__)),
        "resources", "models"
    )
    os.makedirs(models_dir, exist_ok=True)
    print("Models directory: {}".format(models_dir))

    all_ok = True
    for filename, url in MODELS.items():
        dest = os.path.join(models_dir, filename)
        if os.path.exists(dest):
            print("[OK] {} already present ({:.1f} KB)".format(
                filename, os.path.getsize(dest) / 1024))
            continue

        print("Downloading {}...".format(filename), end=" ", flush=True)
        try:
            urllib.request.urlretrieve(url, dest)
            print("done ({:.1f} KB)".format(os.path.getsize(dest) / 1024))
        except Exception as e:
            print("FAILED: {}".format(e))
            all_ok = False

    if all_ok:
        print("\nAll models ready. You can now run: python main.py")
    else:
        print("\nSome downloads failed. Check your internet connection and retry.")

if __name__ == "__main__":
    main()
