"""Find the best free Gemini Flash model your key can use and save it to .env.

Run: backend\\.venv\\Scripts\\python setup\\pick_gemini_model.py
Model names change often, so this asks the API instead of hard-coding one.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"


def read_env() -> dict:
    vals = {}
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip()
    return vals


def write_env_value(key: str, value: str) -> None:
    text = ENV.read_text(encoding="utf-8") if ENV.exists() else ""
    if re.search(rf"^{key}=.*$", text, flags=re.M):
        text = re.sub(rf"^{key}=.*$", f"{key}={value}", text, flags=re.M)
    else:
        text += f"\n{key}={value}\n"
    ENV.write_text(text, encoding="utf-8")


def version_key(name: str):
    nums = re.findall(r"(\d+(?:\.\d+)?)", name)
    v = float(nums[0]) if nums else 0.0
    preview = 1 if ("preview" in name or "exp" in name) else 0
    return (v, -preview)


def main() -> int:
    env = read_env()
    key = env.get("GEMINI_API_KEY", "")
    if not key:
        print("    !!  GEMINI_API_KEY is empty in .env - add it, then rerun this script.")
        return 1
    try:
        from google import genai
    except ImportError:
        print("    !!  google-genai not installed - run install.bat first.")
        return 1

    client = genai.Client(api_key=key)
    try:
        models = list(client.models.list())
    except Exception as e:  # bad key, network, etc.
        print(f"    !!  could not list models: {e}")
        return 1

    names = []
    for m in models:
        actions = getattr(m, "supported_actions", None) or []
        name = m.name.replace("models/", "")
        if "generateContent" in actions and "flash" in name and "lite" not in name \
                and "image" not in name and "tts" not in name and "live" not in name and "audio" not in name:
            names.append(name)
    if not names:
        print("    !!  no Flash text models visible for this key.")
        return 1

    names.sort(key=version_key, reverse=True)
    chosen = None
    for name in names[:6]:  # try newest first; some may be paid-only for this project
        try:
            r = client.models.generate_content(model=name, contents="Reply with the single word: ready")
            if r and r.text:
                chosen = name
                break
        except Exception as e:
            print(f"    ..  {name} not usable on this key ({str(e)[:80]})")
    if not chosen:
        print("    !!  none of the Flash models answered. Check quota at https://aistudio.google.com")
        return 1

    write_env_value("GEMINI_MODEL", chosen)
    print(f"    OK  Gemini works. Using model: {chosen} (saved as GEMINI_MODEL in .env)")
    print(f"        other Flash models on your key: {', '.join(n for n in names if n != chosen)[:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
