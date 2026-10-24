"""Run the dashboard with a Groq key entered in the terminal."""

import getpass
import os


def main():
    if not os.environ.get("GROQ_API_KEY", "").strip():
        try:
            key = getpass.getpass("Groq API key: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            return

        if not key:
            print("No key entered.")
            return

        os.environ["GROQ_API_KEY"] = key

    from app import app

    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)


if __name__ == "__main__":
    main()
