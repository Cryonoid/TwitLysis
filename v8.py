import time
import random
import traceback
import json
import os
import re
import math
import shutil
import zipfile
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import yaml
import nltk
from nltk.corpus import stopwords
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from langdetect import detect, LangDetectException
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException, TimeoutException, NoSuchElementException, SessionNotCreatedException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager

# Output directory paths
RAW_TWEETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tweets", "raw")
RESULTS_TWEETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tweets", "results")

# Existing error_tracker and SEARCH_TERMS
error_tracker = {
    "driver_setup": {"status": "not_started", "error": None},
    "page_load": {"status": "not_started", "error": None},
    "page_scroll": {"status": "not_started", "error": None},
    "tweet_extraction": {"status": "not_started", "error": None},
    "nlp_processing": {"status": "not_started", "error": None},
    "deduplication": {"status": "not_started", "error": None},
    "file_operations": {"status": "not_started", "error": None},
    "captcha_detection": {"status": "not_started", "error": None},
    "auth_verification": {"status": "not_started", "error": None},
}

SEARCH_TERMS = {
    "technology": ["AI", "Machine Learning", "Blockchain", "Python Programming", "Cloud Computing", "Data Science"],
    "entertainment": ["Netflix", "Marvel", "Taylor Swift", "Movie Releases", "Gaming News"],
    "news": ["Breaking News", "Climate Change", "Politics", "World Events", "COVID Updates"],
    "sports": ["NBA", "Soccer", "Tennis", "Olympics", "Formula 1"],
    "business": ["Startup Funding", "Stock Market", "Entrepreneurship", "Business Strategy", "Crypto"]
}

# Expanded pool of user agents for anti-detection
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]

# Brand-to-product alias mapping for enhanced keyword matching (opt-in via Alias Search toggle)
BRAND_ALIASES = {
    "anthropic": ["claude", "claude code", "claude opus", "claude sonnet", "claude haiku"],
    "openai": ["chatgpt", "gpt", "gpt-4", "gpt-5", "codex", "dall-e", "sora"],
    "google": ["gemini", "bard", "deepmind", "google ai"],
    "meta": ["llama", "meta ai", "facebook ai"],
    "tesla": ["elon musk", "cybertruck", "model 3", "model y"],
    "solana": ["sol", "$sol"],
    "bitcoin": ["btc", "$btc", "satoshi"],
    "ethereum": ["eth", "$eth", "vitalik"],
    "microsoft": ["copilot", "azure ai", "bing ai"],
    "apple": ["apple intelligence", "siri ai"],
    "nvidia": ["nvda", "cuda", "tensorrt"],
}

# Pump-and-dump signal phrases for context-aware spam detection
PUMP_DUMP_SIGNALS = {
    "high": [
        "100x", "1000x", "10000x",
        "buy now before", "last chance to buy",
        "don't miss out", "dont miss out", "next moonshot",
        "guaranteed profit", "easy money", "free money",
        "send .* sol to", "send .* eth to",
        "airdrop live", "free airdrop",
        "stealth launch", "just launched",
        "guaranteed returns", "passive income guaranteed",
    ],
    "medium": [
        "lfg", "to the moon",
        "gem alert", "hidden gem",
        "presale", "whitelist",
        "join telegram", "join discord",
        "not financial advice",
        "dyor",
    ],
}

# Category display icons for search suggestion chips
CATEGORY_ICONS = {
    "technology": "\U0001f4bb",
    "entertainment": "\U0001f3ac",
    "news": "\U0001f4f0",
    "sports": "\u26bd",
    "business": "\U0001f4bc",
}

def pick_random_search_term() -> str:
    """Pick a random term from SEARCH_TERMS categories."""
    categories = list(SEARCH_TERMS.keys())
    if not categories:
        return "AI"
    category = random.choice(categories)
    terms = SEARCH_TERMS.get(category) or []
    if not terms:
        return "AI"
    term = random.choice(terms)
    print(f"[INFO] Auto-selected search term from '{category}': {term}")
    return term

def load_cookies(config_file="twitter_cookies.json"):
    """
    Load auth cookies from environment first, then fall back to the JSON cookie file.
    """
    try:
        env_token = os.getenv("TWITTER_AUTH_TOKEN")
        env_ct0 = os.getenv("TWITTER_CT0")
        if env_token:
            print("[DEBUG] Using auth cookies from environment variables.")
            return {
                "auth_token": env_token.strip(),
                "ct0": env_ct0.strip() if env_ct0 else None,
            }

        if os.path.exists(config_file):
            with open(config_file, "r", encoding="utf-8") as f:
                cookies = json.load(f)

            auth_token = cookies.get("auth_token")
            ct0 = cookies.get("ct0")
            if not auth_token:
                print(f"[WARNING] No auth_token found in {config_file}")
                return None

            print(f"[DEBUG] Auth token loaded successfully from {config_file}.")
            return {
                "auth_token": str(auth_token).strip(),
                "ct0": str(ct0).strip() if ct0 else None,
            }

        print(f"[WARNING] Cookie file {config_file} not found.")
        return None
    except Exception as e:
        print(f"[ERROR] Failed to load cookies from {config_file}: {str(e)}")
        return None

def _is_login_or_challenge_page(driver):
    """Return (is_login_or_challenge, reason) based on URL/title/DOM markers."""
    try:
        current_url_lower = driver.current_url.lower()
        page_title_lower = driver.title.lower()

        if "x.com/i/flow/login" in current_url_lower or "twitter.com/i/flow/login" in current_url_lower:
            return True, "login_flow_url"
        if "login on x" in page_title_lower or "log in to x" in page_title_lower:
            return True, "login_page_title"
        if "x.com/account/access" in current_url_lower or "x.com/i/flow" in current_url_lower:
            return True, "access_or_flow_interstitial"

        login_inputs = [
            (By.XPATH, "//input[@name='session[username_or_email]']"),
            (By.XPATH, "//input[@autocomplete='current-password']"),
            (By.XPATH, "//a[contains(@href, '/i/flow/login')]")
        ]
        for by, locator in login_inputs:
            if driver.find_elements(by, locator):
                return True, "login_dom_marker"

        return False, "not_login_or_challenge"
    except Exception:
        return False, "check_failed"

def verify_authenticated_session(driver, search_term, attempt, log_fn):
    """
    Verify login state immediately after cookie injection to avoid false scraper failures.
    """
    try:
        log_fn("[AUTH] Verifying authenticated session state before search navigation...")
        driver.get("https://x.com/home")
        time.sleep(random.uniform(2.5, 4.5))

        login_or_challenge, reason = _is_login_or_challenge_page(driver)
        if login_or_challenge:
            save_debug_html(driver.page_source, search_term, attempt, f"auth_failed_{reason}")
            return False, f"Authentication not active after cookie apply ({reason})."

        logged_in_markers = [
            (By.XPATH, "//a[@data-testid='AppTabBar_Home_Link']"),
            (By.XPATH, "//button[@data-testid='SideNav_AccountSwitcher_Button']"),
            (By.XPATH, "//a[contains(@href, '/compose/post') or contains(@href, '/compose/tweet')]")
        ]

        marker_found = False
        for by, locator in logged_in_markers:
            if driver.find_elements(by, locator):
                marker_found = True
                break

        if not marker_found:
            save_debug_html(driver.page_source, search_term, attempt, "auth_uncertain")
            return False, "Could not confirm logged-in UI markers after cookie apply."

        log_fn("[AUTH] Session verification passed.")
        return True, "verified"
    except Exception as e:
        save_debug_html(driver.page_source, search_term, attempt, "auth_check_exception")
        return False, f"Auth verification error: {str(e)}"

def save_debug_html(content, search_term, attempt, reason):
    """
    Save debug HTML files inside the debug_html directory only.
    """
    try:
        debug_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug_html")
        os.makedirs(debug_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_term = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in str(search_term))
        safe_reason = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in str(reason))
        filename = f"{safe_reason}_{safe_term}_attempt{attempt}_{timestamp}.html"
        file_path = os.path.join(debug_dir, filename)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"[DEBUG] Saved debug HTML to {file_path}")
        return file_path
    except Exception as e:
        print(f"[ERROR] Failed to save debug HTML: {str(e)}")
        return None

def detect_captcha(driver):
    """
    Detect CAPTCHA presence by checking for known CAPTCHA elements or URLs.
    """
    try:
        captcha_indicators = [
            (By.XPATH, "//div[contains(@class, 'g-recaptcha')]"),
            (By.XPATH, "//input[@id='challenge_response']"),
            (By.XPATH, "//h1[contains(text(), 'Verify you are not a robot')]"),
            (By.XPATH, "//form[contains(@action, 'challenge')]"),
        ]
        for by, value in captcha_indicators:
            if driver.find_elements(by, value):
                return True
        if "x.com/i/flow/captcha" in driver.current_url.lower():
            return True
        return False
    except Exception as e:
        print(f"[ERROR] Error detecting CAPTCHA: {str(e)}")
        return False

def simulate_human_behavior(driver):
    """
    Simulate human-like mouse movements and pauses.
    Uses viewport-safe absolute coordinates instead of relative offsets
    to avoid 'move target out of bounds' errors when near viewport edges.
    """
    try:
        # Get viewport dimensions for safe coordinate generation
        vp_width = driver.execute_script("return window.innerWidth") or 800
        vp_height = driver.execute_script("return window.innerHeight") or 600
        # Move to a random safe point within 80% of viewport center
        safe_x = random.randint(int(vp_width * 0.1), int(vp_width * 0.9))
        safe_y = random.randint(int(vp_height * 0.2), int(vp_height * 0.8))
        body = driver.find_element(By.TAG_NAME, "body")
        actions = ActionChains(driver)
        actions.move_to_element_with_offset(body, safe_x, safe_y).perform()
        time.sleep(random.uniform(0.5, 1.5))
        # Random pause
        time.sleep(random.uniform(1.0, 3.0))
    except Exception:
        # Silently pass — human simulation failure is harmless and non-blocking
        pass

def is_element_stale(element):
    """
    Check if a selenium WebElement has become stale (detached from the DOM).
    """
    try:
        if not element:
            return True
        _ = element.tag_name
        return False
    except Exception:
        return True

def get_fresh_container(driver, container):
    """
    Ensure the scrollable container reference is fresh and not stale.
    If the current container is the top-level fallback (html or body),
    try to re-resolve in case the actual scrollable feed container has rendered.
    """
    if not container or is_element_stale(container):
        return get_scroll_container(driver)
    
    try:
        tag_name = container.tag_name.lower()
        if tag_name in ['html', 'body']:
            better_container = get_scroll_container(driver)
            if better_container:
                better_tag = better_container.tag_name.lower()
                if better_tag not in ['html', 'body']:
                    return better_container
    except Exception:
        pass
        
    return container

def smooth_scroll_down(driver, container=None, distance=800, steps=12):
    """
    Scroll the window or specific container down smoothly in small increments to simulate human scrolling.
    This triggers intersection observers and renders virtualized content naturally.
    """
    try:
        container = get_fresh_container(driver, container)
        is_window_scroll = True
        if container:
            try:
                tag_name = container.tag_name.lower()
                if tag_name not in ['html', 'body']:
                    is_window_scroll = False
            except Exception:
                pass

        step_size = distance / steps
        for _ in range(steps):
            jitter = random.uniform(-10, 10)
            current_step = max(1, int(step_size + jitter))
            if not is_window_scroll:
                container = get_fresh_container(driver, container)
                try:
                    driver.execute_script("arguments[0].scrollBy(0, arguments[1]);", container, current_step)
                except Exception:
                    pass
                try:
                    driver.execute_script(f"window.scrollBy(0, {current_step});")
                except Exception:
                    pass
            else:
                try:
                    driver.execute_script(f"window.scrollBy(0, {current_step});")
                except Exception:
                    pass
            time.sleep(random.uniform(0.04, 0.08))
    except Exception:
        pass

def get_scroll_container(driver):
    """
    Find the actual scrollable element in the page (could be main, div, body etc.)
    Uses tweet ancestor traversal to locate the scrollable container.
    """
    js_find_container = """
    // Try to find the scrollable ancestor of a tweet first (most accurate)
    var tweet = document.querySelector('article[data-testid="tweet"]');
    if (tweet) {
        var parent = tweet.parentElement;
        while (parent && parent !== document.body) {
            if (parent.classList && parent.classList.contains('r-150rngu')) {
                return parent;
            }
            var style = window.getComputedStyle(parent);
            if (style.overflowY === 'auto' || style.overflowY === 'scroll') {
                return parent;
            }
            parent = parent.parentElement;
        }
    }

    // Direct lookup for X.com's scroll column
    var r150 = document.querySelector('.r-150rngu');
    if (r150) {
        return r150;
    }

    // Lookup for primary column wrapper
    var primaryCol = document.querySelector('[data-testid="primaryColumn"]');
    if (primaryCol) {
        var parent = primaryCol.parentElement;
        while (parent && parent !== document.body) {
            var style = window.getComputedStyle(parent);
            if (style.overflowY === 'auto' || style.overflowY === 'scroll') {
                return parent;
            }
            parent = parent.parentElement;
        }
    }

    return document.scrollingElement || document.documentElement || document.body;
    """
    try:
        return driver.execute_script(js_find_container)
    except Exception:
        return None

def get_container_scroll_height(driver, container):
    """
    Get the scrollHeight of the scrollable container or document.body.
    """
    try:
        container = get_fresh_container(driver, container)
        win_height = driver.execute_script("return document.body.scrollHeight || document.documentElement.scrollHeight || 0;")
        if not container:
            return win_height
        try:
            cont_height = driver.execute_script("return arguments[0].scrollHeight;", container)
            return max(win_height, cont_height)
        except Exception:
            return win_height
    except Exception:
        return 0

def get_container_scroll_position(driver, container):
    """
    Get the current vertical scroll position of the container or window (active target only).
    """
    try:
        container = get_fresh_container(driver, container)
        win_pos = driver.execute_script("return window.pageYOffset || window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0;")
        is_window_scroll = True
        if container:
            try:
                tag_name = container.tag_name.lower()
                if tag_name not in ['html', 'body']:
                    is_window_scroll = False
            except Exception:
                pass
        
        if is_window_scroll:
            return win_pos
        else:
            try:
                cont_pos = driver.execute_script("return arguments[0].scrollTop || 0;", container)
                return max(win_pos, cont_pos)
            except Exception:
                return win_pos
    except Exception:
        return 0

def get_container_scroll_potential(driver, container):
    """
    Get the remaining scrollable distance (potential) of the container or window.
    """
    try:
        container = get_fresh_container(driver, container)
        win_height = driver.execute_script("return document.documentElement.scrollHeight || document.body.scrollHeight || 0;")
        win_client = driver.execute_script("return window.innerHeight || document.documentElement.clientHeight || document.body.clientHeight || 0;")
        win_top = driver.execute_script("return window.pageYOffset || window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0;")
        win_potential = max(0, win_height - win_client - win_top)
        
        is_window_scroll = True
        if container:
            try:
                tag_name = container.tag_name.lower()
                if tag_name not in ['html', 'body']:
                    is_window_scroll = False
            except Exception:
                pass
        
        if is_window_scroll:
            return win_potential
        else:
            try:
                cont_height = driver.execute_script("return arguments[0].scrollHeight || 0;", container)
                cont_client = driver.execute_script("return arguments[0].clientHeight || 0;", container)
                cont_top = driver.execute_script("return arguments[0].scrollTop || 0;", container)
                cont_potential = max(0, cont_height - cont_client - cont_top)
                return max(win_potential, cont_potential)
            except Exception:
                return win_potential
    except Exception:
        return 0

def get_chrome_version():
    """
    Get the installed Chrome browser version or return a default compatible version.
    """
    try:
        import subprocess
        import re
        import platform
        
        system = platform.system()
        if system == "Windows":
            try:
                # Method 1: Using registry
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
                version, _ = winreg.QueryValueEx(key, "version")
                return version
            except:
                # Method 2: Using PowerShell
                try:
                    cmd = r'(Get-Item -Path "$env:PROGRAMFILES\Google\Chrome\Application\chrome.exe").VersionInfo.FileVersion'
                    version = subprocess.check_output(["powershell", "-command", cmd], 
                                                     stderr=subprocess.DEVNULL).decode('utf-8').strip()
                    return version
                except:
                    # Method 3: Using default location
                    try:
                        cmd = r'(Get-Item -Path "C:\Program Files\Google\Chrome\Application\chrome.exe").VersionInfo.FileVersion'
                        version = subprocess.check_output(["powershell", "-command", cmd], 
                                                         stderr=subprocess.DEVNULL).decode('utf-8').strip()
                        return version
                    except:
                        # Fall back to a known working version
                        return "114.0.5735.90"
        
        elif system == "Linux":
            # Try to get version from Chrome binary
            try:
                process = subprocess.Popen(['google-chrome', '--version'], 
                                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                out, err = process.communicate()
                version = re.search(r'[\d\.]+', out.decode('utf-8')).group(0)
                return version
            except:
                # Fall back to a known working version
                return "114.0.5735.90"
        
        elif system == "Darwin":  # macOS
            try:
                process = subprocess.Popen(['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '--version'], 
                                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                out, err = process.communicate()
                version = re.search(r'[\d\.]+', out.decode('utf-8')).group(0)
                return version
            except:
                # Fall back to a known working version
                return "114.0.5735.90"
        
        # If all detection methods fail, return a known working version
        return "114.0.5735.90"
    
    except Exception as e:
        print(f"[WARNING] Failed to detect Chrome version: {e}")
        # Return a safe version that has good ChromeDriver compatibility
        return "114.0.5735.90"



def get_chrome_major_version(version_string: str) -> int:
    """Return major version number from a browser version string."""
    try:
        return int(str(version_string).split(".")[0])
    except Exception:
        return 0

def _path_without_chromedriver(path_value: str) -> str:
    """Return PATH with directories containing chromedriver removed."""
    if not path_value:
        return path_value
    driver_name = "chromedriver.exe" if os.name == "nt" else "chromedriver"
    cleaned = []
    for entry in path_value.split(os.pathsep):
        candidate = os.path.join(entry, driver_name)
        if os.path.exists(candidate):
            continue
        cleaned.append(entry)
    return os.pathsep.join(cleaned)

def _platform_key_for_cft() -> str:
    """Return Chrome-for-Testing platform key for current OS."""
    if os.name == "nt":
        return "win64"
    if os.uname().sysname.lower() == "darwin":
        # Keep x64 default for compatibility with current setup.
        return "mac-x64"
    return "linux64"

def _version_key(version_str: str):
    """Comparable key for dotted numeric versions."""
    try:
        return tuple(int(p) for p in version_str.split("."))
    except Exception:
        return (0,)

def _get_or_download_matching_chromedriver(chrome_major: int, log_fn=None):
    """
    Download a matching ChromeDriver from Chrome-for-Testing for the given major version.
    Returns local executable path or None.
    """
    def _log(msg):
        if log_fn:
            log_fn(msg)

    if chrome_major <= 0:
        return None

    project_root = os.path.dirname(os.path.abspath(__file__))
    cache_dir = os.path.join(project_root, "drivers", "chromedriver", str(chrome_major))
    os.makedirs(cache_dir, exist_ok=True)

    exe_name = "chromedriver.exe" if os.name == "nt" else "chromedriver"
    cached_exe = os.path.join(cache_dir, exe_name)
    if os.path.exists(cached_exe):
        _log(f"[SETUP] Using cached matching ChromeDriver: {cached_exe}")
        return cached_exe

    index_url = "https://googlechromelabs.github.io/chrome-for-testing/known-good-versions-with-downloads.json"
    _log("[SETUP] Fetching Chrome-for-Testing driver index...")

    try:
        with urllib.request.urlopen(index_url, timeout=30) as response:
            index_data = json.loads(response.read().decode("utf-8"))
    except Exception as e:
        _log(f"[WARNING] Could not fetch Chrome-for-Testing index: {str(e)}")
        return None

    versions = index_data.get("versions", [])
    prefix = f"{chrome_major}."
    candidates = [v for v in versions if str(v.get("version", "")).startswith(prefix)]
    if not candidates:
        _log(f"[WARNING] No Chrome-for-Testing driver entry found for Chrome major {chrome_major}.")
        return None

    candidates.sort(key=lambda x: _version_key(str(x.get("version", "0"))))
    selected = candidates[-1]
    selected_version = selected.get("version", "unknown")

    platform_key = _platform_key_for_cft()
    downloads = selected.get("downloads", {}).get("chromedriver", [])
    item = next((d for d in downloads if d.get("platform") == platform_key), None)
    if not item:
        _log(f"[WARNING] No ChromeDriver download for platform '{platform_key}' in version {selected_version}.")
        return None

    zip_url = item.get("url")
    if not zip_url:
        _log("[WARNING] Missing ChromeDriver download URL in Chrome-for-Testing index.")
        return None

    zip_path = os.path.join(cache_dir, f"chromedriver_{selected_version}_{platform_key}.zip")
    _log(f"[SETUP] Downloading ChromeDriver {selected_version} from Chrome-for-Testing...")

    try:
        urllib.request.urlretrieve(zip_url, zip_path)
    except Exception as e:
        _log(f"[WARNING] Failed downloading ChromeDriver zip: {str(e)}")
        return None

    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            members = archive.namelist()
            target = next((m for m in members if m.endswith(exe_name)), None)
            if not target:
                _log("[WARNING] Downloaded zip does not contain chromedriver executable.")
                return None
            archive.extract(target, cache_dir)
            extracted = os.path.join(cache_dir, target)

        # Move executable to stable location for reuse.
        shutil.move(extracted, cached_exe)

        # Best-effort cleanup of extracted folders and zip.
        try:
            os.remove(zip_path)
        except Exception:
            pass

        _log(f"[SETUP] Downloaded matching ChromeDriver to: {cached_exe}")
        return cached_exe
    except Exception as e:
        _log(f"[WARNING] Failed to extract ChromeDriver zip: {str(e)}")
        return None

def _parse_engagement_for_relevancy(tweet):
    """Parse engagement_raw aria-labels into numeric values for relevancy weighting."""
    result = {"replies": 0, "retweets": 0, "likes": 0, "views": 0}
    for label in tweet.get("engagement_raw", []):
        label_lower = label.lower()
        parts = label.replace(",", "").split()
        if len(parts) >= 2 and parts[0].isdigit():
            num = int(parts[0])
            if "repl" in label_lower:
                result["replies"] = num
            elif "repost" in label_lower or "retweet" in label_lower:
                result["retweets"] = num
            elif "like" in label_lower:
                result["likes"] = num
            elif "view" in label_lower:
                result["views"] = num
    return result


def load_aliases(config_file="aliases.yaml"):
    """Load brand->product alias mappings. Merges aliases.yaml (if exists) with built-in BRAND_ALIASES."""
    aliases = {k: list(v) for k, v in BRAND_ALIASES.items()}
    try:
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), config_file)
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                user_aliases = yaml.safe_load(f) or {}
            for key, vals in user_aliases.items():
                key_lower = key.strip().lower()
                if key_lower in aliases:
                    aliases[key_lower] = list(set(aliases[key_lower] + [v.lower() for v in vals]))
                else:
                    aliases[key_lower] = [v.lower() for v in vals]
            print(f"[ALIAS] Loaded {len(user_aliases)} custom alias entries from {config_file}")
    except Exception as e:
        print(f"[WARNING] Could not load aliases from {config_file}: {e}")
    return aliases


def detect_tweet_language(text):
    """Detect language of tweet text. Returns ISO 639-1 code (e.g., 'en', 'ja', 'zh-cn')."""
    if not text or not text.strip():
        return "en"
    try:
        return detect(text)
    except LangDetectException:
        # Fallback: detect CJK via Unicode ranges
        if re.search(r'[\u3040-\u309f\u30a0-\u30ff]', text):  # Hiragana/Katakana → Japanese
            return 'ja'
        if re.search(r'[\uac00-\ud7af]', text):  # Hangul → Korean
            return 'ko'
        if re.search(r'[\u4e00-\u9fff]', text):  # CJK Unified → Chinese
            return 'zh'
        return 'en'


def classify_search_context(query):
    """Classify whether a search query is crypto-related or general."""
    query_lower = query.strip().lower()
    crypto_patterns = [
        r'^\$[A-Za-z]{2,10}$',
        r'^0x[a-fA-F0-9]{40}$',
        r'^[A-Za-z0-9]{32,44}$',
        r'\b(token|coin|dex|swap|pump|memecoin|nft|defi|airdrop|staking)\b',
    ]
    known_crypto = {
        'bitcoin', 'btc', 'ethereum', 'eth', 'solana', 'sol', 'cardano', 'ada',
        'dogecoin', 'doge', 'xrp', 'ripple', 'polkadot', 'avalanche', 'matic',
        'polygon', 'chainlink', 'uniswap', 'aave', 'litecoin', 'cosmos',
        'near', 'arbitrum', 'optimism', 'sui', 'aptos', 'sei', 'jupiter',
        'bonk', 'pepe', 'shiba', 'floki', 'kaspa', 'render', 'injective',
        'crypto', 'blockchain', 'web3', 'bullrun', 'bull run',
    }
    if any(re.search(p, query_lower) for p in crypto_patterns):
        return 'crypto'
    if query_lower in known_crypto:
        return 'crypto'
    return 'general'


def calculate_spam_score(tweet, search_context, search_term):
    """
    Calculate spam penalty (0.0 = clean, up to 1.0 = definitely spam).
    Context-aware: crypto searches treat wallet addresses differently.
    Returns (penalty_float, list_of_reason_strings).
    """
    penalty = 0.0
    text = tweet.get("text", "")
    text_lower = text.lower()
    username = tweet.get("username", "")
    search_lower = search_term.strip().lower()
    reasons = []

    # Signal 1: Wallet/contract address (context-dependent)
    wallet_matches = re.findall(r'[A-Za-z0-9]{32,44}', text)
    if wallet_matches:
        if search_context == 'general':
            penalty += 0.40
            reasons.append("wallet_address_in_general_search")
        elif search_context == 'crypto':
            search_clean = re.sub(r'[^A-Za-z0-9]', '', search_lower)
            for wallet in wallet_matches:
                if search_clean not in wallet.lower():
                    penalty += 0.40
                    reasons.append("unrelated_wallet_in_crypto_search")
                    break

    # Signal 2: Very short tweet + URL only
    text_without_urls = re.sub(r'https?://\S+', '', text).strip()
    urls_in_text = re.findall(r'https?://\S+', text)
    if len(text_without_urls) < 20 and urls_in_text:
        penalty += 0.30
        reasons.append("short_text_with_url")

    # Signal 3: Bot-like username pattern
    username_clean = username.lstrip("@")
    if re.match(r'^[a-z]+\d{5,}$', username_clean, re.IGNORECASE):
        penalty += 0.15
        reasons.append("bot_username_pattern")

    # Signal 4: Pump-and-dump language (curated dictionary)
    found_high = False
    for phrase in PUMP_DUMP_SIGNALS.get("high", []):
        pattern = re.escape(phrase) if '.*' not in phrase else phrase
        if re.search(pattern, text_lower):
            if search_context == 'crypto' and search_lower in text_lower:
                penalty += 0.10  # Reduced penalty if about the searched coin
            else:
                penalty += 0.25
            reasons.append(f"pump_dump_high:{phrase}")
            found_high = True
            break

    if not found_high:
        for phrase in PUMP_DUMP_SIGNALS.get("medium", []):
            if phrase.lower() in text_lower:
                penalty += 0.10
                reasons.append(f"pump_dump_medium:{phrase}")
                break

    return min(penalty, 1.0), reasons


def calculate_influence(tweet):
    """
    Calculate influence score based on engagement rate and absolute reach.
    Returns 0.0 - 1.0 score. Used as tweet-level metadata/badge, NOT as a
    relevancy weight (it doesn't measure topical relevance).
    
    CRITICAL: When views=0 (X often hides view counts), we CANNOT compute
    an engagement rate. Dividing by 1 makes any interaction look like 100%
    engagement. Instead, fall back to absolute interactions only.
    """
    eng = _parse_engagement_for_relevancy(tweet)
    raw_views = eng["views"]  # 0 means "not available", not "zero views"
    interactions = eng["likes"] + eng["retweets"] * 2 + eng["replies"]

    if interactions == 0:
        return 0.0

    if raw_views > 0:
        # Views available: use engagement rate + reach
        engagement_rate = interactions / raw_views
        resonance = min(math.sqrt(engagement_rate), 1.0)
        reach = math.log1p(raw_views) / math.log1p(100_000)
        reach = min(reach, 1.0)
        return round(min(resonance * 0.50 + reach * 0.50, 1.0), 3)
    else:
        # Views NOT available: use absolute interactions only (log-scaled)
        # 5 interactions → ~0.14, 20 → ~0.25, 100 → ~0.40, 1000 → ~0.60
        abs_score = math.log1p(interactions) / math.log1p(1_000)
        return round(min(abs_score, 1.0), 3)


def calculate_velocity(tweets):
    """
    Calculate temporal velocity of the tweet stream.
    Returns velocity data including tweets-per-minute, acceleration,
    trend direction classification, and timeline buckets for sparkline charts.
    """
    timestamps = []
    for tweet in tweets:
        ts = tweet.get("timestamp")
        if ts:
            try:
                clean_ts = ts.replace("Z", "+00:00")
                dt = datetime.fromisoformat(clean_ts)
                timestamps.append(dt)
            except (ValueError, TypeError):
                continue

    if len(timestamps) < 2:
        return {
            "velocity_tpm": 0, "acceleration": 0,
            "trend_direction": "insufficient_data",
            "timeline_buckets": [], "tweet_count_with_time": len(timestamps)
        }

    timestamps.sort()
    start_time = timestamps[0]
    end_time = timestamps[-1]
    total_span_minutes = max((end_time - start_time).total_seconds() / 60, 1)

    # Adaptive bucket size: 1-min if span < 10min, else 5-min
    # Fixes chart not showing when all tweets arrive within ~5 minutes
    # (5-min buckets → only 1 bucket → chart hidden at < 2 buckets)
    bucket_minutes = 1 if total_span_minutes < 10 else 5
    buckets = {}
    for ts in timestamps:
        bucket_key = int((ts - start_time).total_seconds() / (bucket_minutes * 60))
        bucket_label = (start_time + timedelta(minutes=bucket_key * bucket_minutes)).strftime("%H:%M")
        buckets[bucket_label] = buckets.get(bucket_label, 0) + 1

    timeline_buckets = [{"time": k, "count": v} for k, v in buckets.items()]
    velocity_tpm = round(len(timestamps) / total_span_minutes, 2)

    # Acceleration: compare first half vs second half rate
    midpoint = timestamps[len(timestamps) // 2]
    first_half = [t for t in timestamps if t <= midpoint]
    second_half = [t for t in timestamps if t > midpoint]
    first_span = max((midpoint - start_time).total_seconds() / 60, 1)
    second_span = max((end_time - midpoint).total_seconds() / 60, 1)
    first_rate = len(first_half) / first_span
    second_rate = len(second_half) / second_span

    acceleration = round((second_rate - first_rate) / first_rate, 2) if first_rate > 0 else (1.0 if second_rate > 0 else 0.0)

    # Classify trend direction
    if acceleration > 0.3 and velocity_tpm > 2:
        trend_direction = "surging"
    elif acceleration > 0.1:
        trend_direction = "growing"
    elif acceleration > -0.1:
        trend_direction = "steady"
    else:
        trend_direction = "fading"

    return {
        "velocity_tpm": velocity_tpm, "acceleration": acceleration,
        "trend_direction": trend_direction,
        "timeline_buckets": timeline_buckets,
        "tweet_count_with_time": len(timestamps)
    }


def _compute_conversation_heat(tweets):
    """
    Compute per-tweet 'conversation heat' score based on temporal clustering.
    Tweets in dense time bursts get higher scores (earned relevancy).
    Returns list of scores (0.0 - 1.0) aligned with tweets list.
    """
    timestamps = []
    for tweet in tweets:
        ts = tweet.get("timestamp")
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                timestamps.append(dt)
            except (ValueError, TypeError):
                timestamps.append(None)
        else:
            timestamps.append(None)

    valid_timestamps = [t for t in timestamps if t is not None]
    if len(valid_timestamps) < 3:
        return [0.5] * len(tweets)  # Neutral score when insufficient temporal data

    heat_scores = []
    window_seconds = 5 * 60  # 5-minute window
    for ts in timestamps:
        if ts is None:
            heat_scores.append(0.5)
            continue
        neighbors = sum(1 for other in valid_timestamps if abs((ts - other).total_seconds()) <= window_seconds)
        density = neighbors / len(valid_timestamps)
        heat_scores.append(round(min(density * 3, 1.0), 3))  # Scale up, cap at 1.0

    return heat_scores


def cluster_tweets(tweets, search_term, n_clusters=None):
    """
    Group tweets into sub-theme clusters using TF-IDF + KMeans.
    Auto-detects optimal k (2-5) using silhouette score if n_clusters is None.
    Returns dict with clusters list and summary text.
    """
    texts = [t.get("text", "") for t in tweets if t.get("text", "").strip()]

    if len(texts) < 6:
        return {
            "clusters": [{"label": search_term, "keywords": [search_term],
                          "tweet_indices": list(range(len(tweets))),
                          "percentage": 100, "count": len(tweets)}],
            "summary": f"{len(tweets)} tweets (too few to cluster)"
        }

    try:
        try:
            nltk.data.find('corpora/stopwords')
        except LookupError:
            nltk.download("stopwords", quiet=True)

        # Multilingual stopwords — English-only filtering causes garbage cluster
        # labels like "Que & El & La" when tweets contain Spanish/Portuguese.
        combined_stop_words = set(stopwords.words("english"))
        for lang in ["spanish", "portuguese", "french", "german", "italian"]:
            try:
                combined_stop_words.update(stopwords.words(lang))
            except OSError:
                pass
        # Social media noise words that TF-IDF often picks up
        combined_stop_words.update([
            "rt", "amp", "via", "lol", "omg", "smh", "tbh", "ngl", "lmao",
            "http", "https", "www", "com", "co", "pic", "twitter",
            "like", "just", "got", "get", "one", "new", "every", "make",
        ])
        stop_words_list = list(combined_stop_words)

        vectorizer = TfidfVectorizer(stop_words=stop_words_list, max_features=500, min_df=2, max_df=0.9)
        tfidf_matrix = vectorizer.fit_transform(texts)
        feature_names = vectorizer.get_feature_names_out()

        if tfidf_matrix.shape[1] < 2:
            return {
                "clusters": [{"label": search_term, "keywords": [search_term],
                              "tweet_indices": list(range(len(tweets))),
                              "percentage": 100, "count": len(tweets)}],
                "summary": f"{len(tweets)} tweets (insufficient vocabulary diversity)"
            }

        # Auto-detect optimal k via silhouette score
        if n_clusters is None:
            best_k, best_score = 2, -1
            for k in range(2, min(6, len(texts))):
                try:
                    km = KMeans(n_clusters=k, random_state=42, n_init=10, max_iter=100)
                    labels = km.fit_predict(tfidf_matrix)
                    if len(set(labels)) < 2:
                        continue
                    score = silhouette_score(tfidf_matrix, labels)
                    if score > best_score:
                        best_score, best_k = score, k
                except Exception:
                    continue
            n_clusters = best_k

        km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10, max_iter=200)
        labels = km.fit_predict(tfidf_matrix)

        # Map text indices back to tweet indices
        text_to_tweet_idx = [idx for idx, t in enumerate(tweets) if t.get("text", "").strip()]

        clusters = []
        for cid in range(n_clusters):
            member_text_indices = [i for i, l in enumerate(labels) if l == cid]
            member_tweet_indices = [text_to_tweet_idx[i] for i in member_text_indices if i < len(text_to_tweet_idx)]
            if not member_text_indices:
                continue

            centroid = km.cluster_centers_[cid]
            top_indices = centroid.argsort()[-3:][::-1]
            keywords = [feature_names[i] for i in top_indices if centroid[i] > 0] or [search_term]
            label = " & ".join(kw.title() for kw in keywords[:3])
            percentage = round(len(member_text_indices) / len(texts) * 100)

            clusters.append({"label": label, "keywords": keywords,
                             "tweet_indices": member_tweet_indices,
                             "percentage": percentage, "count": len(member_text_indices)})

        clusters.sort(key=lambda c: c["count"], reverse=True)
        theme_parts = [f"{c['label']} ({c['percentage']}%)" for c in clusters[:4]]
        summary = f"{len(tweets)} tweets across {len(clusters)} themes: {', '.join(theme_parts)}"
        return {"clusters": clusters, "summary": summary}

    except Exception as e:
        print(f"[WARNING] Clustering failed: {e}")
        return {
            "clusters": [{"label": search_term, "keywords": [search_term],
                          "tweet_indices": list(range(len(tweets))),
                          "percentage": 100, "count": len(tweets)}],
            "summary": f"{len(tweets)} tweets (clustering unavailable)"
        }


def calculate_relevancy_score(tweets: list, search_term: str, use_aliases: bool = False) -> tuple:
    """
    Multi-signal relevancy scoring v3.1 with 4 weighted signals:
      - TF-IDF cosine similarity (30%)
      - Enhanced keyword match (35%) — with optional alias expansion
      - Hashtag overlap (15%)
      - Engagement normalization (20%) — log-scaled within batch

    Design decisions (v3.1 fixes):
      - Influence is computed but stored as METADATA ONLY (badge display).
        It measures social reach, not topical relevance — including it in
        weights inflates scores for viral but off-topic tweets.
      - Conversation heat REMOVED. It's degenerate for live scraping where
        all tweets arrive within ~5 minutes (uniform heat → zero discrimination).
      - Percentile normalization REMOVED. It forces scores into a uniform
        distribution where the average is always ~50, destroying actual signal
        variance between relevant and irrelevant content.
      - Spam is FLAGGED as metadata only, not multiplied into scores.
        Users can see spam badges; scores remain explainable.
      - Trend score = median of top-25% (not mean of all including spam).

    Returns (tweets with scores, overall trend score).
    """
    error_tracker["nlp_processing"]["status"] = "in_progress"

    if not tweets:
        print("[WARNING] No tweets to process for relevancy scoring.")
        error_tracker["nlp_processing"]["status"] = "skipped"
        error_tracker["nlp_processing"]["error"] = "No tweets to process"
        return [], 0

    try:
        print("[NLP] Initializing NLTK stopwords...")
        try:
            nltk.data.find('corpora/stopwords')
        except LookupError:
            print("[NLP] Downloading NLTK stopwords resource...")
            nltk.download("stopwords", quiet=True)

        stop_words = set(stopwords.words("english"))
        search_lower = search_term.strip().lower()
        search_words = set(search_lower.split()) - stop_words

        # Load aliases if enabled
        aliases = []
        if use_aliases:
            all_aliases = load_aliases()
            aliases = all_aliases.get(search_lower, [])
            if aliases:
                print(f"[NLP] Alias search enabled. Aliases for '{search_term}': {aliases}")

        # Detect search context for spam scoring
        search_context = classify_search_context(search_term)
        print(f"[NLP] Search context classified as: {search_context}")

        texts = [t.get("text", "") for t in tweets if t.get("text")]
        if not texts:
            print("[WARNING] No valid tweet texts for NLP processing.")
            error_tracker["nlp_processing"]["status"] = "skipped"
            error_tracker["nlp_processing"]["error"] = "No valid tweet texts"
            for tweet in tweets:
                if "relevancy_score" not in tweet:
                    tweet["relevancy_score"] = 0
            return tweets, 0

        # --- Signal 1: TF-IDF cosine similarity (30%) ---
        # NOTE: Raw TF-IDF of a 1-2 word query vs full tweets produces tiny values
        # (0.05-0.15). This compresses 30% of the weight into a narrow band,
        # causing all scores to cluster around 40. Batch min-max normalization
        # spreads the values across 0-1 so the best tweet gets ~1.0.
        print("[NLP] Signal 1/4: TF-IDF cosine similarity...")
        tfidf_scores = [0.0] * len(texts)
        all_docs = [search_term] + texts
        try:
            if len(set(all_docs)) > 1:
                vectorizer = TfidfVectorizer(stop_words=list(stop_words))
                tfidf_matrix = vectorizer.fit_transform(all_docs)
                sim_scores = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:]).flatten()
                tfidf_scores = list(sim_scores)
                # Batch min-max normalization: stretch to 0-1 range
                tfidf_min = min(tfidf_scores)
                tfidf_max = max(tfidf_scores)
                if tfidf_max > tfidf_min:
                    tfidf_scores = [(s - tfidf_min) / (tfidf_max - tfidf_min) for s in tfidf_scores]
                    print(f"[NLP] TF-IDF batch-normalized: raw range [{tfidf_min:.3f}, {tfidf_max:.3f}] → [0, 1]")
            else:
                tfidf_scores = [1.0] * len(texts)
        except Exception as e_tfidf:
            print(f"[WARNING] TF-IDF calculation failed: {e_tfidf}")
            tfidf_scores = [0.0] * len(texts)

        # --- Signal 2: Enhanced keyword match (35%) ---
        print("[NLP] Signal 2/4: Enhanced keyword matching...")
        keyword_scores = []
        # For short queries (≤4 chars, e.g. "sol", "eth", "btc"), use word-boundary
        # matching to avoid false positives like "sol" matching "solution", "console".
        use_word_boundary = len(search_lower.replace(" ", "")) <= 4
        # Build a compiled pattern for word-boundary matching (handles $SOL, #Solana, SOL, sol etc.)
        if use_word_boundary:
            _wb_pattern = re.compile(
                r'(?<![a-z0-9#$])' + re.escape(search_lower) + r'(?![a-z0-9])',
                re.IGNORECASE
            )
            # Also match ticker variants: $SOL, #sol*, SOL
            _ticker_pattern = re.compile(
                r'(?:\$' + re.escape(search_lower) + r'|\#' + re.escape(search_lower) + r'\w*)',
                re.IGNORECASE
            )
        for text in texts:
            text_lower_t = text.lower()
            matched = False
            if use_word_boundary:
                if _wb_pattern.search(text) or _ticker_pattern.search(text):
                    keyword_scores.append(1.0)
                    matched = True
            else:
                if search_lower in text_lower_t:
                    keyword_scores.append(1.0)
                    matched = True
            if not matched:
                if use_aliases and aliases:
                    best_alias = max(
                        (0.8 for a in aliases if a.lower() in text_lower_t),
                        default=0.0
                    )
                    if best_alias > 0:
                        keyword_scores.append(best_alias)
                    elif search_words:
                        text_words = set(text_lower_t.split()) - stop_words
                        overlap = len(search_words & text_words)
                        keyword_scores.append(min(overlap / len(search_words), 1.0) if search_words else 0.0)
                    else:
                        keyword_scores.append(0.0)
                elif search_words:
                    text_words = set(text_lower_t.split()) - stop_words
                    overlap = len(search_words & text_words)
                    keyword_scores.append(min(overlap / len(search_words), 1.0))
                else:
                    keyword_scores.append(0.0)

        # --- Signal 3: Hashtag overlap (15%) ---
        print("[NLP] Signal 3/4: Hashtag relevancy...")
        hashtag_scores = []
        for i, tweet in enumerate(tweets):
            if i >= len(texts):
                break
            hashtags = tweet.get("hashtags", [])
            if not hashtags:
                hashtag_scores.append(0.0)
                continue
            hashtag_text = " ".join(h.lower().lstrip("#") for h in hashtags)
            if search_lower.replace(" ", "") in hashtag_text.replace(" ", ""):
                hashtag_scores.append(1.0)
            elif search_words:
                ht_words = set(hashtag_text.split())
                overlap = len(search_words & ht_words)
                hashtag_scores.append(min(overlap / len(search_words), 1.0))
            else:
                hashtag_scores.append(0.0)
        while len(hashtag_scores) < len(texts):
            hashtag_scores.append(0.0)

        # --- Signal 4: Engagement normalization (20%) ---
        print("[NLP] Signal 4/4: Engagement scoring...")
        raw_engagements = []
        for i, tweet in enumerate(tweets):
            if i >= len(texts):
                break
            eng = _parse_engagement_for_relevancy(tweet)
            total_eng = eng["likes"] + eng["retweets"] * 2 + eng["replies"]
            raw_engagements.append(total_eng)
        while len(raw_engagements) < len(texts):
            raw_engagements.append(0)

        max_eng = max(raw_engagements) if raw_engagements else 0
        if max_eng > 0:
            engagement_scores = [math.log1p(e) / math.log1p(max_eng) for e in raw_engagements]
        else:
            engagement_scores = [0.5] * len(texts)

        # --- Signal 5: Influence scoring (metadata only, NOT a relevancy weight) ---
        # Influence measures social reach/resonance — not topical relevance.
        # Stored per-tweet for badge display but excluded from the combined score.
        print("[NLP] Computing influence scores (metadata only, not weighted)...")
        influence_scores = []
        for i, tweet in enumerate(tweets):
            if i >= len(texts):
                break
            influence_scores.append(calculate_influence(tweet))
        while len(influence_scores) < len(texts):
            influence_scores.append(0.0)

        # --- Combine signals with weights ---
        # NOTE: Only 4 signals are used for relevancy. Influence and conversation
        # heat are EXCLUDED:
        #   - Influence: measures social reach, not topical relevance
        #   - Conv. heat: degenerate for live scraping (all tweets in same ~5min window)
        W_TFIDF = 0.30
        W_KEYWORD = 0.35
        W_HASHTAG = 0.15
        W_ENGAGEMENT = 0.20

        print(f"[NLP] Combining 4 relevancy signals (TF-IDF {int(W_TFIDF*100)}%, "
              f"Keyword {int(W_KEYWORD*100)}%, Hashtag {int(W_HASHTAG*100)}%, "
              f"Engagement {int(W_ENGAGEMENT*100)}%)...")

        raw_scores = []
        for i in range(min(len(texts), len(tweets))):
            combined = (
                tfidf_scores[i] * W_TFIDF +
                keyword_scores[i] * W_KEYWORD +
                hashtag_scores[i] * W_HASHTAG +
                engagement_scores[i] * W_ENGAGEMENT
            )
            raw_scores.append(combined)

        # --- Spam detection (flag only, NO score modification) ---
        # Spam used to silently crush scores via multiplication. Now it's
        # flagged as metadata so the user can see WHY a tweet is suspicious,
        # without the score becoming an unexplainably low number.
        print("[NLP] Applying context-aware spam detection (flag-only)...")
        spam_count = 0
        for i in range(min(len(raw_scores), len(tweets))):
            spam_penalty, spam_reasons = calculate_spam_score(tweets[i], search_context, search_term)
            if spam_penalty > 0:
                tweets[i]["spam_flag"] = True
                tweets[i]["spam_reasons"] = spam_reasons
                tweets[i]["spam_penalty"] = round(spam_penalty, 2)
                spam_count += 1
            else:
                tweets[i]["spam_flag"] = False

        if spam_count > 0:
            print(f"[NLP] Flagged {spam_count} tweets as potential spam (scores preserved).")

        # --- Detect language per tweet ---
        # TODO: FUTURE — Multilingual sentiment (VADER only supports English).
        # Non-English tweets currently receive neutral sentiment scores.
        # Future options: xml-roberta, language-specific VADER ports, or translation pipeline.
        print("[NLP] Detecting tweet languages...")
        lang_counts = {}
        for tweet in tweets:
            lang = detect_tweet_language(tweet.get("text", ""))
            tweet["language"] = lang
            lang_counts[lang] = lang_counts.get(lang, 0) + 1
        print(f"[NLP] Language distribution: {dict(sorted(lang_counts.items(), key=lambda x: -x[1])[:5])}")

        # --- Store influence score per tweet (metadata for badge display) ---
        for i, tweet in enumerate(tweets):
            if i < len(influence_scores):
                tweet["influence_score"] = influence_scores[i]

        # --- Direct linear scaling (NO percentile normalization) ---
        # Percentile normalization was the root cause of 49-score stagnation:
        # it forces a uniform distribution where avg always = N/2/(N-1) ≈ 50.
        # This kills actual signal variance — a batch of spam and a batch of
        # perfectly relevant tweets would both average to 50.
        #
        # Instead: scale the raw combined score directly to 0-100.
        # The combined signal is already 0.0-1.0 (all inputs are 0-1, weights sum to 1).
        print("[NLP] Applying direct linear scoring (no percentile normalization)...")
        if raw_scores:
            for i in range(min(len(raw_scores), len(tweets))):
                # Direct 0-1 → 0-100 mapping
                score = int(round(raw_scores[i] * 100))
                # Bonus for Top tab tweets: Twitter's algorithm already curated these
                # as higher quality/engagement, so they deserve a relevancy uplift
                if tweets[i].get("source_tab") == "top":
                    score += 8
                tweets[i]["relevancy_score"] = max(0, min(score, 100))

        # Any remaining tweets without scores
        for tweet in tweets:
            if "relevancy_score" not in tweet:
                tweet["relevancy_score"] = 0

        # --- Trend score: median of top-25% (quality of best content, not avg of all) ---
        scores_list = sorted([t.get("relevancy_score", 0) for t in tweets], reverse=True)
        if scores_list:
            top_quartile = scores_list[:max(1, len(scores_list) // 4)]
            trend_score = top_quartile[len(top_quartile) // 2]  # median of top 25%
        else:
            trend_score = 0

        print(f"[NLP] Relevancy complete. Trend score (median top-25%): {trend_score}")
        print(f"[NLP] Score range: {min(scores_list)}-{max(scores_list)}, "
              f"mean: {sum(scores_list)//len(scores_list)}")
        error_tracker["nlp_processing"]["status"] = "success"
        return tweets, trend_score

    except Exception as e:
        print(f"[ERROR] Error in relevancy calculation: {str(e)}")
        traceback.print_exc()
        error_tracker["nlp_processing"]["status"] = "failed"
        error_tracker["nlp_processing"]["error"] = str(e)

        for tweet in tweets:
            if "relevancy_score" not in tweet:
                tweet["relevancy_score"] = 0
        return tweets, 0


def save_to_yaml(data: dict, filename: str, is_raw: bool = False) -> bool:
    """
    Save data to YAML file in the designated directory
    """
    current_op_status = "in_progress"
    try:
        # Determine the appropriate directory based on type of data
        if is_raw:
            output_dir = RAW_TWEETS_DIR
        else:
            output_dir = RESULTS_TWEETS_DIR
            
        # Create the directories if they don't exist
        os.makedirs(output_dir, exist_ok=True)
            
        # Full path of the output file
        filepath = os.path.join(output_dir, filename)
            
        with open(filepath, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
        print(f"[FILE] Successfully saved data to {filepath}")
        current_op_status = "success"
        if "results.yaml" in filename or "raw.yaml" in filename:
            error_tracker["file_operations"]["status"] = "success"
        return True
    except Exception as e:
        print(f"[ERROR] Failed to save to {filename}: {str(e)}")
        current_op_status = "failed"
        if "results.yaml" in filename or "raw.yaml" in filename:
            error_tracker["file_operations"]["status"] = "failed"
            error_tracker["file_operations"]["error"] = str(e)
        return False

def build_failure_summary() -> str:
    """Return a compact failure summary with the first failed step as likely root cause."""
    ordered_steps = [
        "driver_setup",
        "auth_verification",
        "page_load",
        "captcha_detection",
        "page_scroll",
        "tweet_extraction",
        "deduplication",
        "nlp_processing",
        "file_operations",
    ]
    failed = []
    for step in ordered_steps:
        state = error_tracker.get(step, {})
        if state.get("status") == "failed":
            failed.append((step, state.get("error") or "unknown error"))

    if not failed:
        return "No explicit failed step recorded. Check debug_html snapshots for runtime context."

    root_step, root_error = failed[0]
    details = "; ".join([f"{step}: {err}" for step, err in failed])
    return f"Root cause: {root_step} -> {root_error}. Failed steps: {details}"

def extract_visible_tweets(driver, seen_tweet_ids, tweets, error_tracker, search_term, attempt, log) -> int:
    """
    Extract currently visible tweets from the DOM, adding any new ones to tweets and seen_tweet_ids.
    Returns the number of new tweets found in this pass.
    """
    tweets_found_this_pass = 0
    try:
        error_tracker["tweet_extraction"]["status"] = "in_progress"
        articles = driver.find_elements(By.XPATH, "//article[@data-testid='tweet']")

        for article in articles:
            tweet_data = {}
            tweet_id = None
            try:
                status_links = article.find_elements(By.XPATH, ".//a[contains(@href, '/status/')]")
                for link_el in status_links:
                    href = link_el.get_attribute('href')
                    if href and '/status/' in href:
                        potential_id = href.split('/status/')[-1].split('?')[0]
                        if potential_id.isdigit():
                            tweet_id = potential_id
                            tweet_data["tweet_url"] = href.split('?')[0]
                            break
                if tweet_id and tweet_id in seen_tweet_ids:
                    continue
                tweet_data["id"] = tweet_id
            except Exception:
                pass

            if not tweet_id:
                pass

            try:
                text_elements = article.find_elements(By.XPATH, ".//div[@data-testid='tweetText']")
                if text_elements:
                    tweet_data["text"] = text_elements[0].text
                else:
                    lang_divs = article.find_elements(By.XPATH, ".//div[@lang]")
                    if lang_divs:
                        tweet_data["text"] = lang_divs[0].text
                    else:
                        continue
            except NoSuchElementException:
                continue
            except Exception:
                continue

            if not tweet_id and "text" in tweet_data:
                tweet_id = f"hash_{hash(tweet_data['text'][:50])}"
                if tweet_id in seen_tweet_ids:
                    continue
                tweet_data["id"] = tweet_id

            if not tweet_data.get("id"):
                continue

            try:
                user_name_elements = article.find_elements(By.XPATH, ".//div[@data-testid='User-Name']//span[contains(text(), '@')]")
                if user_name_elements:
                    tweet_data["username"] = user_name_elements[0].text
                else:
                    user_name_block = article.find_elements(By.XPATH, ".//div[@data-testid='User-Name']")
                    if user_name_block:
                        tweet_data["username"] = user_name_block[0].text.split('\n')[0]
                    else:
                        tweet_data["username"] = "unknown_user"
            except Exception:
                tweet_data["username"] = "unknown_user_exception"

            # Ensure tweet_url exists via fallback construction
            if not tweet_data.get("tweet_url") and tweet_data.get("username") and tweet_id:
                clean_user = tweet_data["username"].lstrip("@")
                if clean_user and tweet_id and not tweet_id.startswith("hash_"):
                    tweet_data["tweet_url"] = f"https://x.com/{clean_user}/status/{tweet_id}"

            try:
                hashtag_links = article.find_elements(By.XPATH, ".//a[contains(@href, '/hashtag/')]")
                tweet_data["hashtags"] = [link.text for link in hashtag_links if link.text.startswith('#')]
            except Exception:
                tweet_data["hashtags"] = []

            # Extract engagement metrics (likes, retweets, replies) — best effort
            try:
                group_els = article.find_elements(By.XPATH, ".//div[@role='group']//button")
                metrics = []
                for btn in group_els:
                    aria = btn.get_attribute("aria-label") or ""
                    if aria:
                        metrics.append(aria)
                tweet_data["engagement_raw"] = metrics
            except Exception:
                tweet_data["engagement_raw"] = []

            # Extract timestamp from tweet
            try:
                time_elements = article.find_elements(By.XPATH, ".//time")
                if time_elements:
                    tweet_data["timestamp"] = time_elements[0].get_attribute("datetime")
                else:
                    tweet_data["timestamp"] = None
            except Exception:
                tweet_data["timestamp"] = None

            if "text" in tweet_data and tweet_data["text"].strip():
                tweets.append(tweet_data)
                seen_tweet_ids.add(tweet_data["id"])
                tweets_found_this_pass += 1

        error_tracker["tweet_extraction"]["status"] = "success"
    except Exception as e:
        log(f"[ERROR] Error during visible tweet extraction: {str(e)}")
        error_tracker["tweet_extraction"]["status"] = "partial"
        error_tracker["tweet_extraction"]["error"] = str(e)
    return tweets_found_this_pass

def scrape_twitter_trends(search_term: str, max_retries=2, request_delay=10, progress_callback=None, search_tab="live", max_scroll_override=None) -> list:
    """
    Scrape tweets related to the search term from X with enhanced anti-ban features.
    Returns a list of tweet dictionaries or empty list if failed.
    
    If progress_callback is provided, it will be called with status messages.
    max_scroll_override: Override default max_scroll_attempts (for per-tab budgeting).
    """
    def log(message):
        print(message)
        if progress_callback:
            progress_callback(message)
            
    driver = None
    attempt = 1
    tweets = []
    rate_limit_requests = 20
    requests_made = 0

    while attempt <= max_retries:
        log(f"[ATTEMPT {attempt}/{max_retries}] Scraping for '{search_term}'...")
        try:
            # Driver Setup
            error_tracker["driver_setup"]["status"] = "in_progress"
            log(f"[SETUP] Initializing Chrome WebDriver...")

            chrome_options = Options()
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--lang=en-US,en;q=0.9")
            chrome_options.add_argument(f"user-agent={random.choice(USER_AGENTS)}")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            chrome_options.add_argument("--disable-infobars")
            chrome_options.add_argument(f"--window-size={random.randint(1200, 1920)},{random.randint(800, 1080)}")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--profile-directory=Default")
            chrome_options.add_argument("--disable-plugins-discovery")

            # Try multiple strategies to initialize the Chrome WebDriver
            driver_initialized = False
            chrome_version = get_chrome_version()
            chrome_major = get_chrome_major_version(chrome_version)
            log(f"[SETUP] Detected Chrome version: {chrome_version} (major={chrome_major})")

            # For Chrome 115+, avoid webdriver-manager/local-driver fallback because they often
            # pin to stale binaries and cause session mismatch errors on newer Chrome.
            if chrome_major >= 115 and not driver_initialized:
                original_path = os.environ.get("PATH", "")
                try:
                    log("[SETUP] Chrome >=115 detected; forcing Selenium Manager direct initialization...")
                    if os.path.exists("chromedriver.exe"):
                        log("[WARNING] Found ./chromedriver.exe in project root; this can force an incompatible driver.")
                        log("[HINT] Remove or rename local chromedriver.exe to allow Selenium Manager to resolve a matching version.")
                    detected_local = shutil.which("chromedriver")
                    if detected_local:
                        log(f"[SETUP] Found local chromedriver in PATH: {detected_local}")
                        log("[SETUP] Temporarily removing chromedriver directories from PATH for this launch.")
                    os.environ["PATH"] = _path_without_chromedriver(original_path)
                    driver = webdriver.Chrome(options=chrome_options)
                    driver_initialized = True
                    log("[SETUP] Selenium Manager direct initialization succeeded.")
                except SessionNotCreatedException as e:
                    log(f"[WARNING] Direct init session mismatch: {str(e)}")
                    log("[HINT] Trying Chrome-for-Testing fallback with an exact matching driver...")
                except Exception as e:
                    log(f"[WARNING] Direct init failed for Chrome >=115: {str(e)}")
                    log("[HINT] Trying Chrome-for-Testing fallback with an exact matching driver...")
                finally:
                    os.environ["PATH"] = original_path

                if not driver_initialized:
                    try:
                        matching_driver_path = _get_or_download_matching_chromedriver(chrome_major, log)
                        if matching_driver_path:
                            service = Service(executable_path=matching_driver_path)
                            driver = webdriver.Chrome(service=service, options=chrome_options)
                            driver_initialized = True
                            log("[SETUP] Matching Chrome-for-Testing driver initialization succeeded.")
                        else:
                            raise WebDriverException("Matching Chrome-for-Testing driver could not be resolved.")
                    except Exception as e:
                        log(f"[ERROR] Chrome-for-Testing fallback failed: {str(e)}")
                        error_tracker["driver_setup"]["status"] = "failed"
                        error_tracker["driver_setup"]["error"] = f"Direct and Chrome-for-Testing fallbacks failed: {str(e)}"
                        attempt += 1
                        continue

            # Legacy fallback path for older Chrome versions only.
            if chrome_major < 115 and not driver_initialized:
                try:
                    log("[SETUP] Trying webdriver_manager with default settings...")
                    service = Service(ChromeDriverManager().install())
                    driver = webdriver.Chrome(service=service, options=chrome_options)
                    driver_initialized = True
                    log("[SETUP] webdriver_manager initialization succeeded.")
                except SessionNotCreatedException as e:
                    log(f"[WARNING] webdriver_manager session mismatch: {str(e)}")
                    log("[HINT] Detected browser/driver mismatch. Update ChromeDriver or rely on Selenium Manager with latest Selenium.")
                except Exception as e:
                    log(f"[WARNING] webdriver_manager failed: {str(e)}")

            if chrome_major < 115 and not driver_initialized:
                for path in ["chromedriver.exe", "./chromedriver.exe", "/usr/local/bin/chromedriver"]:
                    if os.path.exists(path):
                        try:
                            log(f"[SETUP] Trying local ChromeDriver at {path}...")
                            service = Service(executable_path=path)
                            driver = webdriver.Chrome(service=service, options=chrome_options)
                            driver_initialized = True
                            log(f"[SETUP] Local ChromeDriver succeeded: {path}")
                            break
                        except SessionNotCreatedException as e:
                            log(f"[WARNING] Local driver mismatch at {path}: {str(e)}")
                            log("[HINT] Detected browser/driver mismatch. Update ChromeDriver or rely on Selenium Manager with latest Selenium.")
                        except Exception as e:
                            log(f"[WARNING] Local ChromeDriver at {path} failed: {str(e)}")

            if chrome_major < 115 and not driver_initialized:
                try:
                    log("[SETUP] Final fallback: direct Chrome WebDriver initialization...")
                    driver = webdriver.Chrome(options=chrome_options)
                    driver_initialized = True
                    log("[SETUP] Final direct initialization succeeded.")
                except SessionNotCreatedException as e:
                    log(f"[ERROR] All WebDriver initialization methods failed: {str(e)}")
                    log("[HINT] Detected browser/driver mismatch. Update ChromeDriver or rely on Selenium Manager with latest Selenium.")
                    error_tracker["driver_setup"]["status"] = "failed"
                    error_tracker["driver_setup"]["error"] = f"All initialization methods failed: {str(e)}"
                    attempt += 1
                    continue
                except Exception as e:
                    log(f"[ERROR] All WebDriver initialization methods failed: {str(e)}")
                    error_tracker["driver_setup"]["status"] = "failed"
                    error_tracker["driver_setup"]["error"] = f"All initialization methods failed: {str(e)}"
                    attempt += 1
                    continue

            if not driver_initialized:
                raise WebDriverException("Failed to initialize Chrome WebDriver with any available method")

            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            driver.execute_script("window.navigator.chrome = { runtime: {} };")
            driver.execute_script("Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });")
            error_tracker["driver_setup"]["status"] = "success"
            
            # Load cookies for authentication
            cookies = load_cookies()
            if cookies and cookies.get("auth_token"):
                log("[AUTH] Applying authentication cookies...")
                try:
                    driver.get("https://x.com")
                    time.sleep(random.uniform(2, 4))
                    driver.add_cookie({
                        "name": "auth_token",
                        "value": cookies["auth_token"],
                        "domain": ".x.com",
                        "secure": True,
                        "httpOnly": True,
                        "path": "/",
                    })
                    if cookies.get("ct0"):
                        ct0_val = cookies["ct0"]
                        if isinstance(ct0_val, list):
                            ct0_val = ct0_val[0] if ct0_val else ""
                        driver.add_cookie({
                            "name": "ct0",
                            "value": str(ct0_val).strip(),
                            "domain": ".x.com",
                            "secure": True,
                            "httpOnly": False,
                            "path": "/",
                        })
                    log("[AUTH] Cookies applied successfully.")
                    error_tracker["auth_verification"]["status"] = "success"
                except Exception as e:
                    log(f"[ERROR] Failed to set cookies: {str(e)}")
                    error_tracker["page_load"]["status"] = "failed"
                    error_tracker["page_load"]["error"] = f"Cookie application failed: {str(e)}"
                    attempt += 1
                    continue
            else:
                error_tracker["auth_verification"]["status"] = "skipped"
                error_tracker["auth_verification"]["error"] = "No auth_token available"
                log("[WARNING] No auth_token available; proceeding without authenticated session.")

            # Page Load with CAPTCHA Detection
            error_tracker["page_load"]["status"] = "in_progress"
            if search_tab == "top":
                url = f"https://x.com/search?q={urllib.parse.quote(search_term)}&src=typed_query"
            else:
                url = f"https://x.com/search?q={urllib.parse.quote(search_term)}&src=typed_query&f=live"
            log(f"[NETWORK] Accessing URL: {url}")

            try:
                driver.get(url)
                WebDriverWait(driver, 20).until(
                    EC.any_of(
                        EC.presence_of_element_located((By.XPATH, "//article[@data-testid='tweet']")),
                        EC.presence_of_element_located((By.XPATH, "//input[@name='session[username_or_email]']")),
                        EC.presence_of_element_located((By.XPATH, "//input[@name='text' and @type='text']")),
                        EC.url_contains("x.com/i/flow/login"),
                        EC.title_contains("Login on X")
                    )
                )

                # Check for CAPTCHA
                error_tracker["captcha_detection"]["status"] = "in_progress"
                if detect_captcha(driver):
                    error_tracker["captcha_detection"]["status"] = "failed"
                    error_tracker["captcha_detection"]["error"] = "CAPTCHA detected; stopping to avoid ban risk."
                    log("[ERROR] CAPTCHA detected. Saving page source and stopping to avoid ban risk.")
                    save_debug_html(driver.page_source, search_term, attempt, "captcha")
                    log("[INFO] Please solve the CAPTCHA manually in a browser, update twitter_cookies.json, and try again.")
                    return []
                error_tracker["captcha_detection"]["status"] = "success"

                current_url_lower = driver.current_url.lower()
                page_title_lower = driver.title.lower()
                is_on_search = ("x.com/search" in current_url_lower or
                                "twitter.com/search" in current_url_lower)
                is_on_explore = ("x.com/explore" in current_url_lower or
                                 "twitter.com/explore" in current_url_lower)
                is_on_login_flow, login_reason = _is_login_or_challenge_page(driver)

                if is_on_explore:
                    error_tracker["page_load"]["status"] = "failed"
                    error_message = f"Redirected to Explore page (search query may be malformed or empty). URL: {driver.current_url}"
                    error_tracker["page_load"]["error"] = error_message
                    log(f"[ERROR] {error_message}")
                    save_debug_html(driver.page_source, search_term, attempt, "explore_redirect")
                    attempt += 1
                    continue

                if not is_on_search or is_on_login_flow:
                    error_tracker["page_load"]["status"] = "failed"
                    error_message = f"Redirected or on login/challenge page ({login_reason}). URL: {driver.current_url}, Title: {driver.title}"
                    error_tracker["page_load"]["error"] = error_message
                    log(f"[ERROR] Page load issue: {error_message}")
                    try:
                        tweet_elements = driver.find_elements(By.XPATH, "//article[@data-testid='tweet']")
                        log(f"[DEBUG] Found {len(tweet_elements)} tweet elements on page.")
                    except Exception as e:
                        log(f"[DEBUG] Could not check tweet elements: {str(e)}")
                    save_debug_html(driver.page_source, search_term, attempt, "redirect")
                    attempt += 1
                    continue

                log("[INFO] Successfully loaded search page, proceeding to check content.")
                error_tracker["page_load"]["status"] = "success"

            except TimeoutException:
                error_tracker["page_load"]["status"] = "failed"
                error_tracker["page_load"]["error"] = "Page load timeout: Key elements not found."
                log(f"[ERROR] Page load timed out. Current URL: {driver.current_url}, Title: {driver.title}")
                save_debug_html(driver.page_source, search_term, attempt, "timeout")
                attempt += 1
                continue
            except Exception as e:
                error_tracker["page_load"]["status"] = "failed"
                error_tracker["page_load"]["error"] = str(e)
                log(f"[ERROR] Page load failed with exception: {str(e)}. URL: {driver.current_url}")
                attempt += 1
                continue

            # Scrape Tweets
            seen_tweet_ids = set()
            last_height = driver.execute_script("return document.body.scrollHeight")
            scroll_attempts = 0
            max_scroll_attempts = max_scroll_override if max_scroll_override else 15
            consecutive_no_new_tweets_scrolls = 0
            max_consecutive_no_new_tweets = 5
            recent_yields = []  # Rolling window for dynamic yield-based stopping

            log(f"[SCRAPE] Starting to scroll and collect tweets (max {max_scroll_attempts} scrolls, tab={search_tab})...")
            error_tracker["page_scroll"]["status"] = "in_progress"
            scrape_start_time = time.time()
            SCRAPE_TIMEOUT_SECONDS = 300  # 5-minute wall-clock guard

            # Extract tweets already visible on initial page load before scrolling
            initial_tweets = extract_visible_tweets(
                driver, seen_tweet_ids, tweets, error_tracker,
                search_term, attempt, log
            )
            if initial_tweets > 0:
                log(f"[SCRAPE] Initial extraction: Found {initial_tweets} tweets before scrolling.")

            while scroll_attempts < max_scroll_attempts and requests_made < rate_limit_requests:
                scroll_attempts += 1
                requests_made += 1
                tweets_found_this_scroll_pass = 0

                # Wall-clock timeout guard
                elapsed = time.time() - scrape_start_time
                if elapsed > SCRAPE_TIMEOUT_SECONDS:
                    log(f"[SCRAPE] Wall-clock timeout ({SCRAPE_TIMEOUT_SECONDS}s) reached after {scroll_attempts-1} scrolls. Stopping with {len(tweets)} tweets.")
                    break

                try:
                    # Dismiss cookie banners
                    try:
                        cookie_btn = driver.find_element(By.XPATH, "//span[contains(text(), 'Refuse non-essential') or contains(text(), 'Accept all')]")
                        if cookie_btn.is_displayed():
                            cookie_btn.click()
                    except Exception:
                        pass

                    # Phase 1: Incremental scrollBy steps — capture virtualized tweets
                    for _ in range(5):
                        scroll_distance = random.randint(500, 700)
                        driver.execute_script(f"window.scrollBy(0, {scroll_distance});")
                        time.sleep(random.uniform(0.8, 1.5))
                        new_extracted = extract_visible_tweets(
                            driver, seen_tweet_ids, tweets, error_tracker,
                            search_term, attempt, log
                        )
                        tweets_found_this_scroll_pass += new_extracted

                    # Phase 2: scrollTo(bottom) kick — triggers intersection observer
                    # sentinel at the very bottom to load the next batch of tweets
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

                    # Phase 3: Wait for DOM mutation — poll scrollHeight for up to 5s
                    # instead of a blind sleep. Proceed immediately when content loads.
                    pre_kick_height = driver.execute_script("return document.body.scrollHeight")
                    content_loaded = False
                    for _ in range(10):  # 10 polls × 500ms = 5s max
                        time.sleep(0.5)
                        current_height = driver.execute_script("return document.body.scrollHeight")
                        if current_height > pre_kick_height:
                            content_loaded = True
                            break
                    
                    if content_loaded:
                        # New content appeared — extract immediately
                        new_extracted = extract_visible_tweets(
                            driver, seen_tweet_ids, tweets, error_tracker,
                            search_term, attempt, log
                        )
                        tweets_found_this_scroll_pass += new_extracted

                    # Human-like pause + rate limit respect
                    time.sleep(random.uniform(1.5, 3.0))
                    time.sleep(request_delay)
                    simulate_human_behavior(driver)

                    if tweets_found_this_scroll_pass > 0:
                        log(f"[SCRAPE] Scroll {scroll_attempts}: Found {tweets_found_this_scroll_pass} new tweets. Total: {len(tweets)}")
                        consecutive_no_new_tweets_scrolls = 0
                    else:
                        consecutive_no_new_tweets_scrolls += 1
                        log(f"[SCRAPE] Scroll {scroll_attempts}: No new tweets. Consecutive empty scrolls: {consecutive_no_new_tweets_scrolls}")

                        # Stall recovery: scroll UP ~2000px then back down to force
                        # X.com to re-render the virtualized list and trigger fresh loading
                        if consecutive_no_new_tweets_scrolls >= 2:
                            log("[SCRAPE] Attempting stall recovery: scrolling up and back down...")
                            driver.execute_script("window.scrollBy(0, -2000);")
                            time.sleep(random.uniform(1.0, 2.0))
                            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                            time.sleep(random.uniform(2.0, 3.0))
                            recovery_extracted = extract_visible_tweets(
                                driver, seen_tweet_ids, tweets, error_tracker,
                                search_term, attempt, log
                            )
                            if recovery_extracted > 0:
                                log(f"[SCRAPE] Stall recovery found {recovery_extracted} new tweets! Total: {len(tweets)}")
                                consecutive_no_new_tweets_scrolls = 0

                    # Dynamic yield-based stopping: track rolling 3-scroll average.
                    # If yield drops below 2 tweets/scroll and we already have ≥30,
                    # stop early instead of wasting scrolls on a depleted feed.
                    recent_yields.append(tweets_found_this_scroll_pass)
                    if len(recent_yields) > 3:
                        recent_yields.pop(0)
                    if (len(recent_yields) >= 3 and
                            sum(recent_yields) / len(recent_yields) < 2 and
                            len(tweets) >= 30):
                        avg_yield = sum(recent_yields) / len(recent_yields)
                        log(f"[SCRAPE] Yield dropping (avg {avg_yield:.1f}/scroll over last 3). "
                            f"Stopping with {len(tweets)} tweets.")
                        break

                    if consecutive_no_new_tweets_scrolls >= max_consecutive_no_new_tweets:
                        log(f"[SCRAPE] Reached {max_consecutive_no_new_tweets} consecutive scrolls with no new tweets. Stopping.")
                        break

                    # Height-based stall detection
                    new_height = driver.execute_script("return document.body.scrollHeight")
                    if new_height == last_height and scroll_attempts > 2:
                        if consecutive_no_new_tweets_scrolls > 2:
                            log(f"[SCRAPE] Scroll height unchanged and no new tweets. Stopping.")
                            break
                    last_height = new_height

                    if requests_made >= rate_limit_requests:
                        log(f"[RATE LIMIT] Reached max requests ({rate_limit_requests}) for this session.")
                        break

                except WebDriverException as e_scroll_wd:
                    log(f"[ERROR] WebDriverException during scroll/extraction: {str(e_scroll_wd)}")
                    error_tracker["page_scroll"]["status"] = "failed"
                    error_tracker["page_scroll"]["error"] = str(e_scroll_wd)
                    break
                except Exception as e_extract_generic:
                    log(f"[ERROR] Generic error during scroll/extraction: {str(e_extract_generic)}")
                    error_tracker["tweet_extraction"]["status"] = "partial"
                    error_tracker["tweet_extraction"]["error"] = str(e_extract_generic)
                    consecutive_no_new_tweets_scrolls += 1

            error_tracker["page_scroll"]["status"] = "success" if scroll_attempts > 0 else "skipped"
            log(f"[SCRAPE] Scraping phase complete. Found {len(tweets)} potential tweets from {scroll_attempts} scroll attempts.")

            try:
                save_debug_html(driver.page_source, search_term, attempt, "final_page")
            except Exception as e_save_final:
                log(f"[ERROR] Failed to save final debug HTML: {str(e_save_final)}")

            if not tweets:
                error_tracker["deduplication"]["status"] = "skipped"
                error_tracker["deduplication"]["error"] = "No tweets collected to deduplicate"
                return []

            try:
                error_tracker["deduplication"]["status"] = "in_progress"
                unique_tweets_final = []
                seen_texts_final = set()
                for tweet in tweets:
                    text_content = tweet.get("text", "").strip().lower()
                    if text_content and text_content not in seen_texts_final:
                        seen_texts_final.add(text_content)
                        unique_tweets_final.append(tweet)
                
                if len(tweets) != len(unique_tweets_final):
                    log(f"[DEDUPE] Final text-based deduplication: {len(tweets)} -> {len(unique_tweets_final)} tweets")
                else:
                    log(f"[DEDUPE] No further duplicates found by text from {len(tweets)} tweets.")
                
                # Tag each tweet with the source tab
                for tweet in unique_tweets_final:
                    if "source_tab" not in tweet:
                        tweet["source_tab"] = "top" if search_tab == "top" else "latest"
                
                error_tracker["deduplication"]["status"] = "success"
                return unique_tweets_final
            except Exception as e_dedupe_final:
                log(f"[ERROR] Final deduplication error: {str(e_dedupe_final)}")
                error_tracker["deduplication"]["status"] = "failed"
                error_tracker["deduplication"]["error"] = str(e_dedupe_final)
                return tweets

        except Exception as e_critical:
            log(f"[CRITICAL] Unexpected error in scrape_twitter_trends: {str(e_critical)}")
            for step_key in ["driver_setup", "page_load", "page_scroll", "tweet_extraction"]:
                if error_tracker.get(step_key, {}).get("status") == "in_progress":
                    error_tracker[step_key]["status"] = "failed"
                    error_tracker[step_key]["error"] = f"Aborted due to critical error: {e_critical}"
            attempt += 1
        finally:
            if driver:
                try:
                    driver.quit()
                    log("[CLEANUP] WebDriver closed successfully")
                except Exception as e_quit:
                    log(f"[WARNING] Error closing WebDriver: {str(e_quit)}")
        
        if attempt <= max_retries:
            log(f"[RETRY] Waiting {request_delay} seconds before retrying...")
            time.sleep(request_delay)

    log(f"[FAILURE] All {max_retries} attempts failed for '{search_term}'.")
    return []

def scrape_both_tabs(search_term, progress_callback=None, request_delay=10):
    """
    Scrape both Top and Latest tabs, merge and deduplicate.
    Top tab yields curated, higher-quality tweets (Twitter's algorithm).
    Latest tab yields real-time, higher-volume tweets.
    Uses separate browser sessions per tab (Option A) for stability.
    """
    def log(message):
        print(message)
        if progress_callback:
            progress_callback(message)

    all_tweets = []
    seen_ids = set()

    # Top tab first (higher quality, curated by Twitter's algorithm)
    log("[DUAL-TAB] Scraping Top tab for curated tweets...")
    top_messages = []
    def collect_top(msg):
        top_messages.append(msg)
    top_start = time.time()
    top_tweets = scrape_twitter_trends(
        search_term, search_tab="top",
        progress_callback=collect_top,
        request_delay=request_delay,
        max_scroll_override=10  # Top tab: curated results are finite
    )
    for msg in top_messages:
        if progress_callback:
            progress_callback(msg)
    for t in top_tweets:
        tid = t.get("id")
        if tid and tid not in seen_ids:
            seen_ids.add(tid)
            all_tweets.append(t)
    top_elapsed = time.time() - top_start
    log(f"[DUAL-TAB] Top tab: {len(top_tweets)} tweets scraped, {len(all_tweets)} unique so far. ({top_elapsed:.0f}s)")

    # Latest tab (real-time, volume)
    log("[DUAL-TAB] Scraping Latest tab for real-time tweets...")
    live_messages = []
    def collect_live(msg):
        live_messages.append(msg)
    live_start = time.time()
    live_tweets = scrape_twitter_trends(
        search_term, search_tab="live",
        progress_callback=collect_live,
        request_delay=request_delay,
        max_scroll_override=20  # Latest tab: real-time content keeps flowing
    )
    for msg in live_messages:
        if progress_callback:
            progress_callback(msg)
    live_added = 0
    for t in live_tweets:
        tid = t.get("id")
        if tid and tid not in seen_ids:
            seen_ids.add(tid)
            all_tweets.append(t)
            live_added += 1
    live_elapsed = time.time() - live_start
    log(f"[DUAL-TAB] Latest tab: {len(live_tweets)} tweets scraped, {live_added} new unique added. ({live_elapsed:.0f}s)")
    log(f"[DUAL-TAB] Combined total: {len(all_tweets)} unique tweets from both tabs.")

    return all_tweets


def run_batch_analysis(terms: list, use_aliases=False):
    """
    Run analysis on multiple terms sequentially, yielding progress for each.
    Includes cooldown between terms to avoid rate limiting.
    """
    total = len(terms)
    for idx, term in enumerate(terms, 1):
        yield f"[BATCH {idx}/{total}] ═══ Starting analysis for: '{term}' ═══"
        try:
            for msg in run_twitter_analysis_script(term, use_aliases=use_aliases):
                yield msg
            yield f"[BATCH {idx}/{total}] ✓ Completed '{term}'."
        except Exception as e:
            yield f"[BATCH {idx}/{total}] ✗ Failed '{term}': {str(e)}"
        # Cooldown between terms to avoid rate limiting
        if idx < total:
            cooldown = random.randint(30, 60)
            yield f"[BATCH] Cooling down {cooldown}s before next term..."
            time.sleep(cooldown)
    yield f"[BATCH COMPLETE] All {total} terms analyzed."


def run_twitter_analysis_script(search_term, use_aliases=False):
    """
    Run the Twitter analysis pipeline and yield progress updates.
    Enhanced v3: includes 6-signal relevancy, spam detection, language detection,
    topic clustering, velocity analysis, and influence scoring.
    """
    for step in error_tracker:
        error_tracker[step] = {"status": "not_started", "error": None}
        
    yield f"[START] Analyzing Twitter trend for: '{search_term}'"
    yield "[INFO] This may take a few minutes. Please wait..."
    if use_aliases:
        yield "[INFO] Alias search is enabled."
    
    try:
        # Step 1: Scraping tweets from both Top and Latest tabs
        yield "[STEP 1/5] Scraping tweets from Top and Latest tabs..."
        yield "[INFO] Scraping Top tab first (curated tweets), then Latest tab (real-time)."
        raw_tweets = []
        
        messages = []
        def collect_message(msg):
            messages.append(msg)
        
        raw_tweets = scrape_both_tabs(search_term, progress_callback=collect_message)
        
        for msg in messages:
            yield msg
        
        # Report per-tab breakdown
        top_count = sum(1 for t in raw_tweets if t.get("source_tab") == "top")
        latest_count = sum(1 for t in raw_tweets if t.get("source_tab") == "latest")
        yield f"[INFO] Scraping complete. Found {len(raw_tweets)} unique tweets (Top: {top_count}, Latest: {latest_count})."
        
        if not raw_tweets:
            yield "[ERROR] No tweets found or scraping failed for the given search term."
            yield f"[DIAG] {build_failure_summary()}"
            return

        # Step 2: Save raw tweets
        yield "[STEP 2/5] Saving unique raw tweets..."
        raw_fn = f"{search_term.replace(' ', '_')}_raw_unique.yaml"
        save_to_yaml({"search_term": search_term, "raw_tweets_count": len(raw_tweets), "tweets": raw_tweets}, 
                    raw_fn, is_raw=True)
        yield f"[INFO] Unique raw tweets saved to tweets/raw/{raw_fn}"
        
        # Step 3: Multi-signal analysis & scoring (6 signals + spam + language + influence)
        yield "[STEP 3/5] Analyzing tweets (6-signal relevancy, spam detection, language, influence)..."
        scored_tweets, trend_score = calculate_relevancy_score(raw_tweets, search_term, use_aliases=use_aliases)
        
        # Count analysis stats for reporting
        spam_count = sum(1 for t in scored_tweets if t.get("spam_flag"))
        lang_dist = {}
        for t in scored_tweets:
            lang = t.get("language", "en")
            lang_dist[lang] = lang_dist.get(lang, 0) + 1
        high_influence = sum(1 for t in scored_tweets if t.get("influence_score", 0) > 0.7)
        
        yield f"[INFO] Scored {len(scored_tweets)} tweets. Spam flagged: {spam_count}. High influence: {high_influence}."
        
        # Step 4: Clustering & velocity analysis
        yield "[STEP 4/5] Clustering topics & analyzing velocity..."
        cluster_data = cluster_tweets(scored_tweets, search_term)
        velocity_data = calculate_velocity(scored_tweets)
        
        yield f"[INFO] {cluster_data['summary']}"
        yield f"[INFO] Velocity: {velocity_data['velocity_tpm']} tweets/min, direction: {velocity_data['trend_direction']}"
        
        # Sort tweets by relevancy
        final_tweets = sorted(scored_tweets, key=lambda x: x.get("relevancy_score", 0), reverse=True)
        
        # Step 5: Save results (with enhanced data)
        yield "[STEP 5/5] Saving scored results..."
        out_fn = f"{search_term.replace(' ', '_')}_results.yaml"
        out = {
            "trend_relevancy": trend_score,
            "search_term": search_term,
            "tweets_count": len(final_tweets),
            "search_context": classify_search_context(search_term),
            "velocity": velocity_data,
            "clusters": cluster_data,
            "language_distribution": lang_dist,
            "spam_flagged_count": spam_count,
            "high_influence_count": high_influence,
            "tweets": final_tweets
        }
        save_to_yaml(out, out_fn, is_raw=False)
        yield f"[INFO] Scored results saved to tweets/results/{out_fn}"
        
        # Display summary
        yield f"\n[COMPLETE] Analysis for '{search_term}' completed successfully."
        yield f"[RESULTS] Overall trend relevancy score: {trend_score}/100"
        yield f"[RESULTS] Found {len(final_tweets)} relevant tweets."
        yield f"[RESULTS] Trend velocity: {velocity_data['trend_direction']} ({velocity_data['velocity_tpm']} tpm)"
        
        # Output top tweets
        if final_tweets:
            yield "\n[TOP TWEETS]"
            for i, tweet in enumerate(final_tweets[:5]):
                if i >= 5:
                    break
                username = tweet.get('username', 'unknown_user')
                text = tweet.get('text', '')[:100] + ('...' if len(tweet.get('text', '')) > 100 else '')
                score = tweet.get('relevancy_score', 0)
                lang = tweet.get('language', '??')
                spam_tag = ' ⚠SPAM' if tweet.get('spam_flag') else ''
                yield f"[{score:>3}] [{lang}]{spam_tag} {username}: {text}"
        
    except Exception as e:
        import traceback
        yield f"[ERROR] An error occurred: {str(e)}"
        yield f"[DIAG] {build_failure_summary()}"
        traceback.print_exc()
        yield traceback.format_exc()

if __name__ == "__main__":
    try:
        print("Twitter Trend Analysis Tool")
        print("==========================")
        print("[WARNING] This script performs web scraping on X. Use sparingly to avoid account restrictions.")
        
        term = input("Enter a search term (leave blank for random): ").strip()
        if not term:
            term = pick_random_search_term()
        
        start_time = time.time()
        for message in run_twitter_analysis_script(term):
            print(message)
        elapsed_time = time.time() - start_time
        
        print(f"\n[COMPLETE] Analysis for '{term}' completed in {elapsed_time:.1f} seconds.")
    except KeyboardInterrupt:
        print("\n[ABORT] Operation cancelled by user.")
    except Exception as e:
        print(f"\n[CRITICAL] An unexpected error occurred in __main__: {str(e)}")
        traceback.print_exc()
