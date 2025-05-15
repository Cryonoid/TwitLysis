import time
import random
import traceback
import json
import os
from datetime import datetime
from bs4 import BeautifulSoup
import yaml
import nltk
nltk.data.path.append('/home/flip1/nltk_data')
from nltk.corpus import stopwords
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException, TimeoutException, NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
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

def load_cookies(config_file="twitter_cookies.json"):
    """
    Load cookies from a JSON file for authentication.
    Expected format: {"auth_token": "your_auth_token"}
    """
    try:
        if os.path.exists(config_file):
            with open(config_file, "r") as f:
                cookies = json.load(f)
            auth_token = cookies.get("auth_token", None)
            if not auth_token:
                print("[WARNING] No auth_token found in cookie file.")
                return None
            print("[DEBUG] Auth token loaded successfully.")
            return auth_token
        else:
            print(f"[WARNING] Cookie file {config_file} not found.")
            return None
    except Exception as e:
        print(f"[ERROR] Failed to load cookies: {str(e)}")
        return None

def save_debug_html(content, search_term, attempt, reason):
    """
    Save debug HTML with metadata for improved debugging.
    """
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"debug_{reason}_{search_term.replace(' ', '_')}_attempt{attempt}_{timestamp}.html"
        metadata = f"<!-- Debug Info: Search Term: {search_term}, Attempt: {attempt}, Reason: {reason}, Timestamp: {timestamp} -->\n"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(metadata + content)
        print(f"[DEBUG] Saved debug HTML to {filename}")
    except Exception as e:
        print(f"[ERROR] Failed to save debug HTML: {str(e)}")

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
    """
    try:
        actions = ActionChains(driver)
        # Random mouse movement
        actions.move_by_offset(random.randint(-100, 100), random.randint(-100, 100)).perform()
        time.sleep(random.uniform(0.5, 1.5))
        # Random pause
        time.sleep(random.uniform(1.0, 3.0))
    except Exception as e:
        print(f"[WARNING] Failed to simulate human behavior: {str(e)}")

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

def calculate_relevancy_score(tweets: list, search_term: str) -> tuple:
    """
    Calculate relevancy scores for tweets using TF-IDF and cosine similarity.
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
            nltk.download("stopwords", quiet=False)

        stop_words = set(stopwords.words("english"))

        texts = [t.get("text", "") for t in tweets if t.get("text")]
        if not texts:
            print("[WARNING] No valid tweet texts for NLP processing.")
            error_tracker["nlp_processing"]["status"] = "skipped"
            error_tracker["nlp_processing"]["error"] = "No valid tweet texts"
            for tweet in tweets:
                if "relevancy_score" not in tweet: tweet["relevancy_score"] = 0
            return tweets, 0
            
        all_docs = [search_term] + texts
        
        if len(set(all_docs)) <= 1 and len(all_docs) > 1:
            print("[WARNING] All documents are identical or too few unique texts for TF-IDF analysis.")
            mean_score_val = 0
            num_scored = 0
            for i, tweet_text in enumerate(texts):
                if tweet_text.strip().lower() == search_term.strip().lower():
                    tweets[i]["relevancy_score"] = 100
                else:
                    tweets[i]["relevancy_score"] = 75 if search_term.strip().lower() in tweet_text.strip().lower() else 25
                mean_score_val += tweets[i]["relevancy_score"]
                num_scored += 1
            
            trend_score = int(mean_score_val / num_scored) if num_scored > 0 else 0
            error_tracker["nlp_processing"]["status"] = "partial"
            error_tracker["nlp_processing"]["error"] = "Not enough unique content for TF-IDF; used heuristic scoring."
            return tweets, trend_score
        elif len(all_docs) <= 1:
            print("[WARNING] No tweet texts to compare with search term.")
            error_tracker["nlp_processing"]["status"] = "skipped"
            error_tracker["nlp_processing"]["error"] = "No tweet texts for TF-IDF."
            return tweets, 0

        print("[NLP] Calculating TF-IDF vectors...")
        vectorizer = TfidfVectorizer(stop_words=list(stop_words))
        tfidf = vectorizer.fit_transform(all_docs)

        print("[NLP] Computing relevancy scores (cosine similarity)...")
        sim_scores = cosine_similarity(tfidf[0:1], tfidf[1:]).flatten()
        
        for i, score in enumerate(sim_scores):
            if i < len(tweets):
                tweets[i]["relevancy_score"] = int(score * 100)

        trend_score = int(sim_scores.mean() * 100) if len(sim_scores) > 0 else 0
        
        print(f"[NLP] Relevancy calculation complete. Overall trend score: {trend_score}")
        error_tracker["nlp_processing"]["status"] = "success"
        return tweets, trend_score
    except Exception as e:
        print(f"[ERROR] Error in relevancy calculation: {str(e)}")
        traceback.print_exc()
        error_tracker["nlp_processing"]["status"] = "failed"
        error_tracker["nlp_processing"]["error"] = str(e)
        
        for tweet in tweets:
            if "relevancy_score" not in tweet: tweet["relevancy_score"] = 0
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

def scrape_twitter_trends(search_term: str, max_retries=2, request_delay=10, progress_callback=None) -> list:
    """
    Scrape tweets related to the search term from X with enhanced anti-ban features.
    Returns a list of tweet dictionaries or empty list if failed.
    
    If progress_callback is provided, it will be called with status messages.
    """
    def log(message):
        print(message)
        if progress_callback:
            progress_callback(message)
            
    driver = None
    attempt = 1
    tweets = []
    rate_limit_requests = 5
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
            
            # Strategy 1: Using WebDriverManager with specific Chrome version
            if not driver_initialized:
                try:
                    log("[SETUP] Trying webdriver_manager with specific Chrome version...")
                    chrome_version = get_chrome_version()
                    log(f"[SETUP] Detected Chrome version: {chrome_version}")
                    
                    from webdriver_manager.chrome import ChromeDriverManager
                    service = Service(ChromeDriverManager(chrome_type=chrome_version).install())
                    driver = webdriver.Chrome(service=service, options=chrome_options)
                    driver_initialized = True
                    log("[SETUP] Chrome WebDriver initialized successfully with specific version.")
                except Exception as e:
                    log(f"[WARNING] Failed to initialize with specific Chrome version: {str(e)}")
            
            # Strategy 2: Using WebDriverManager with default settings
            if not driver_initialized:
                try:
                    log("[SETUP] Trying webdriver_manager with default settings...")
                    from webdriver_manager.chrome import ChromeDriverManager
                    service = Service(ChromeDriverManager().install())
                    driver = webdriver.Chrome(service=service, options=chrome_options)
                    driver_initialized = True
                    log("[SETUP] Chrome WebDriver initialized successfully with default settings.")
                except Exception as e:
                    log(f"[WARNING] WebDriverManager default approach failed: {str(e)}")
            
            # Strategy 3: Using local ChromeDriver if it exists
            if not driver_initialized:
                for path in ["chromedriver.exe", "./chromedriver.exe", "/usr/local/bin/chromedriver"]:
                    if os.path.exists(path):
                        try:
                            log(f"[SETUP] Trying local ChromeDriver at {path}...")
                            service = Service(executable_path=path)
                            driver = webdriver.Chrome(service=service, options=chrome_options)
                            driver_initialized = True
                            log(f"[SETUP] Chrome WebDriver initialized successfully using local driver at {path}")
                            break
                        except Exception as e:
                            log(f"[WARNING] Local ChromeDriver at {path} failed: {str(e)}")
            
            # Strategy 4: Use direct initialization as last resort
            if not driver_initialized:
                try:
                    log("[SETUP] Trying direct Chrome WebDriver initialization...")
                    driver = webdriver.Chrome(options=chrome_options)
                    driver_initialized = True
                    log("[SETUP] Chrome WebDriver initialized successfully via direct approach.")
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
            auth_token = load_cookies()
            if auth_token:
                log("[AUTH] Applying authentication cookies...")
                try:
                    driver.get("https://x.com")
                    time.sleep(random.uniform(2, 4))
                    driver.add_cookie({
                        "name": "auth_token",
                        "value": auth_token,
                        "domain": ".x.com",
                        "secure": True,
                        "httpOnly": True,
                        "path": "/",
                    })
                    log("[AUTH] Cookies applied successfully.")
                    driver.refresh()
                    time.sleep(random.uniform(2, 4))
                    simulate_human_behavior(driver)
                except Exception as e:
                    log(f"[ERROR] Failed to set cookies: {str(e)}")
                    error_tracker["page_load"]["status"] = "failed"
                    error_tracker["page_load"]["error"] = f"Cookie application failed: {str(e)}"
                    attempt += 1
                    continue

            # Page Load with CAPTCHA Detection
            error_tracker["page_load"]["status"] = "in_progress"
            url = f"https://x.com/search?q={search_term}&src=typed_query&f=live"
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
                is_on_search_or_explore = ("x.com/search" in current_url_lower or "x.com/explore" in current_url_lower or
                                         "twitter.com/search" in current_url_lower or "twitter.com/explore" in current_url_lower)
                is_on_login_flow = ("x.com/i/flow/login" in current_url_lower or
                                  "twitter.com/i/flow/login" in current_url_lower or
                                  "login on x" in page_title_lower or "log in to x" in page_title_lower)

                if not is_on_search_or_explore or is_on_login_flow:
                    error_tracker["page_load"]["status"] = "failed"
                    error_message = f"Redirected or on login page. URL: {driver.current_url}, Title: {driver.title}"
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
            max_scroll_attempts = 3  # Reduced to minimize detection
            consecutive_no_new_tweets_scrolls = 0
            max_consecutive_no_new_tweets = 3

            log("[SCRAPE] Starting to scroll and collect tweets...")
            error_tracker["page_scroll"]["status"] = "in_progress"

            while scroll_attempts < max_scroll_attempts and requests_made < rate_limit_requests:
                scroll_attempts += 1
                requests_made += 1
                tweets_found_this_scroll_pass = 0
                try:
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(random.uniform(3, 5))
                    time.sleep(request_delay)
                    simulate_human_behavior(driver)

                    error_tracker["tweet_extraction"]["status"] = "in_progress"
                    articles = driver.find_elements(By.XPATH, "//article[@data-testid='tweet']")

                    if not articles and scroll_attempts == 1:
                        log("[WARNING] No tweet articles found immediately after page load.")
                        save_debug_html(driver.page_source, search_term, attempt, "no_articles")

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

                        try:
                            hashtag_links = article.find_elements(By.XPATH, ".//a[contains(@href, '/hashtag/')]")
                            tweet_data["hashtags"] = [link.text for link in hashtag_links if link.text.startswith('#')]
                        except Exception:
                            tweet_data["hashtags"] = []

                        if "text" in tweet_data and tweet_data["text"].strip():
                            tweets.append(tweet_data)
                            seen_tweet_ids.add(tweet_data["id"])
                            tweets_found_this_scroll_pass += 1

                    error_tracker["tweet_extraction"]["status"] = "success"

                    if tweets_found_this_scroll_pass > 0:
                        log(f"[SCRAPE] Scroll {scroll_attempts}: Found {tweets_found_this_scroll_pass} new tweets. Total: {len(tweets)}")
                        consecutive_no_new_tweets_scrolls = 0
                    else:
                        consecutive_no_new_tweets_scrolls += 1
                        log(f"[SCRAPE] Scroll {scroll_attempts}: No new tweets. Consecutive empty scrolls: {consecutive_no_new_tweets_scrolls}")

                    if consecutive_no_new_tweets_scrolls >= max_consecutive_no_new_tweets:
                        log(f"[SCRAPE] Reached {max_consecutive_no_new_tweets} consecutive scrolls with no new tweets. Stopping.")
                        break

                    new_height = driver.execute_script("return document.body.scrollHeight")
                    if new_height == last_height and scroll_attempts > 1:
                        if consecutive_no_new_tweets_scrolls > 1:
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

def run_twitter_analysis_script(search_term):
    """
    Run the Twitter analysis and yield progress updates.
    This generator function allows for real-time updates to the frontend.
    """
    for step in error_tracker:
        error_tracker[step] = {"status": "not_started", "error": None}
        
    yield f"[START] Analyzing Twitter trend for: '{search_term}'"
    yield "[INFO] This may take a few minutes. Please wait..."
    
    try:
        # Step 1: Scraping tweets
        yield "[STEP 1/5] Scraping and initial deduplicating tweets..."
        raw_tweets = []
        
        # Create a collector function to yield messages from scraper
        messages = []
        def collect_message(msg):
            messages.append(msg)
            yield msg
        
        # Run the scraper
        raw_tweets = scrape_twitter_trends(search_term, progress_callback=collect_message)
        
        # Pass along any collected messages
        for msg in messages:
            yield msg
            
        yield f"[INFO] Scraping complete. Found {len(raw_tweets)} unique tweets."
        
        if not raw_tweets:
            yield "[ERROR] No tweets found or scraping failed for the given search term."
            return

        # Step 2: Save raw tweets
        yield "[STEP 2/5] Saving unique raw tweets..."
        raw_fn = f"{search_term.replace(' ', '_')}_raw_unique.yaml"
        save_to_yaml({"search_term": search_term, "raw_tweets_count": len(raw_tweets), "tweets": raw_tweets}, 
                    raw_fn, is_raw=True)
        yield f"[INFO] Unique raw tweets saved to tweets/raw/{raw_fn}"
        
        # Step 3: Calculate relevancy scores
        yield "[STEP 3/5] Calculating relevancy scores..."
        scored_tweets, trend_score = calculate_relevancy_score(raw_tweets, search_term)
        
        # Step 4: Sort tweets by relevancy
        yield "[STEP 4/5] Sorting tweets by relevancy..."
        final_tweets = sorted(scored_tweets, key=lambda x: x.get("relevancy_score", 0), reverse=True)
        
        # Step 5: Save results
        yield "[STEP 5/5] Saving scored results..."
        out_fn = f"{search_term.replace(' ', '_')}_results.yaml"
        out = {"trend_relevancy": trend_score, "search_term": search_term, "tweets_count": len(final_tweets), "tweets": final_tweets}
        save_to_yaml(out, out_fn, is_raw=False)
        yield f"[INFO] Scored results saved to tweets/results/{out_fn}"
        
        # Display summary
        yield f"\n[COMPLETE] Analysis for '{search_term}' completed successfully."
        yield f"[RESULTS] Overall trend relevancy score: {trend_score}/100"
        yield f"[RESULTS] Found {len(final_tweets)} relevant tweets."
        
        # Output top tweets
        if final_tweets:
            yield "\n[TOP TWEETS]"
            for i, tweet in enumerate(final_tweets[:5]):
                if i >= 5:
                    break
                username = tweet.get('username', 'unknown_user')
                text = tweet.get('text', '')[:100] + ('...' if len(tweet.get('text', '')) > 100 else '')
                score = tweet.get('relevancy_score', 0)
                yield f"[{score:>3}] {username}: {text}"
        
    except Exception as e:
        import traceback
        yield f"[ERROR] An error occurred: {str(e)}"
        traceback.print_exc()
        yield traceback.format_exc()

if __name__ == "__main__":
    try:
        print("Twitter Trend Analysis Tool")
        print("==========================")
        print("[WARNING] This script performs web scraping on X. Use sparingly to avoid account restrictions.")
        
        term = input("Enter a search term: ").strip()
        
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
