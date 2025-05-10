import time
import random
import traceback
import json
import os
from datetime import datetime
from bs4 import BeautifulSoup
import yaml
import nltk # Keep NLTK imports if used elsewhere
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


# Your error_tracker and SEARCH_TERMS dictionaries remain the same
error_tracker = {
    "driver_setup": {"status": "not_started", "error": None},
    "page_load": {"status": "not_started", "error": None},
    "page_scroll": {"status": "not_started", "error": None},
    "tweet_extraction": {"status": "not_started", "error": None},
    "nlp_processing": {"status": "not_started", "error": None},
    "deduplication": {"status": "not_started", "error": None},
    "file_operations": {"status": "not_started", "error": None},
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

def simulate_human_behavior(driver):
    """
    Simulate human-like mouse movements and pauses.
    """
    try:
        actions = ActionChains(driver)
        # Constrain offsets to smaller range
        actions.move_by_offset(random.randint(-50, 50), random.randint(-50, 50)).perform()
        time.sleep(random.uniform(0.5, 1.5))
        time.sleep(random.uniform(1.0, 3.0))
    except Exception as e:
        print(f"[WARNING] Failed to simulate human behavior: {str(e)}. Skipping movement.")


def select_random_search_term():
    """
    Randomly select a search term from the predefined categories.
    """
    category = random.choice(list(SEARCH_TERMS.keys()))
    term = random.choice(SEARCH_TERMS[category])
    print(f"Randomly selected search term: '{term}' from category: {category}")
    return term

def scrape_twitter_trends(search_term: str) -> list:
    """
    Scrape tweets related to the search term from Twitter.
    Returns a list of tweet dictionaries or empty list if failed.
    """
    driver = None
    # Assuming error_tracker is global or passed appropriately and reset by the caller.

    try:
        error_tracker["driver_setup"]["status"] = "in_progress"
        print(f"[SETUP] Initializing Chrome WebDriver...")
        chrome_driver_path = r"C:\Users\incre\Downloads\chromedriver-win64\chromedriver-win64\chromedriver.exe" # Ensure this is correct

        chrome_options = Options()
        # --- IMPORTANT DEBUGGING TIP ---
        # To see what the browser is actually doing (e.g., login page, CAPTCHA),
        # comment out the next line (headless mode) and run the script.
        # chrome_options.add_argument("--headless")
        # --- END DEBUGGING TIP ---

        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--lang=en-US,en;q=0.9") # More common lang format
        # Use a recent and common user agent. Update this periodically.
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36") # Example, use a current one

        # --- Anti-detection measures ---
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        # --- End Anti-detection ---

        try:
            service = Service(executable_path=chrome_driver_path)
            # Consider using webdriver-manager for automatic driver updates:
            # from webdriver_manager.chrome import ChromeDriverManager
            # service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)

            # --- Further Anti-detection (after driver is initialized) ---
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            # --- End Further Anti-detection ---
            error_tracker["driver_setup"]["status"] = "success"
        except WebDriverException as e:
            error_tracker["driver_setup"]["status"] = "failed"
            error_tracker["driver_setup"]["error"] = str(e)
            print(f"[ERROR] Chrome WebDriver setup failed: {str(e)}")
            return []

        driver.set_window_size(1920, 1080)

        error_tracker["page_load"]["status"] = "in_progress"
        url = f"https://twitter.com/search?q={search_term}&src=typed_query&f=live"
        print(f"[NETWORK] Accessing URL: {url}")

        try:
            driver.get(url)
            # Use WebDriverWait to wait for critical elements indicating page has loaded
            # or redirected to a login/interstitial page.
            # Waiting for <article> (tweets) OR a common login input field.
            WebDriverWait(driver, 25).until(
                EC.any_of(
                    EC.presence_of_element_located((By.XPATH, "//article[@data-testid='tweet']")),
                    EC.presence_of_element_located((By.XPATH, "//input[@name='session[username_or_email]']")), # Classic login
                    EC.presence_of_element_located((By.XPATH, "//input[@name='text' and @type='text']")), # Newer login/username field
                    EC.url_contains("twitter.com/i/flow/login"), # Check for login flow URL
                    EC.title_contains("Login on X") # Check for login page title
                )
            )

            current_url_lower = driver.current_url.lower()
            page_title_lower = driver.title.lower()

            # More robust check for redirection or login page
            # Check if we are on a known search or explore page.
            # If not, or if explicitly on a login flow, then it's a failure.
            is_on_search_or_explore = "twitter.com/search" in current_url_lower or \
                                      "twitter.com/explore" in current_url_lower
            is_on_login_flow = "twitter.com/i/flow/login" in current_url_lower or \
                               "login on x" in page_title_lower or "log in to x" in page_title_lower


            if not is_on_search_or_explore or is_on_login_flow:
                error_tracker["page_load"]["status"] = "failed"
                error_message = f"Redirected or on login page. URL: {driver.current_url}, Title: {driver.title}"
                error_tracker["page_load"]["error"] = error_message
                print(f"[ERROR] Page load issue: {error_message}")
                try:
                    redirected_page_file = f"debug_redirected_{search_term.replace(' ', '_')}.html"
                    with open(redirected_page_file, "w", encoding="utf-8") as f:
                        f.write(driver.page_source)
                    print(f"[DEBUG] Saved redirected page source to {redirected_page_file}")
                except Exception as ex_save:
                    print(f"[ERROR] Could not save redirected page source: {ex_save}")
                return []
            
            print("[INFO] Successfully loaded a Twitter page, proceeding to check content.")
            error_tracker["page_load"]["status"] = "success"

        except TimeoutException:
            error_tracker["page_load"]["status"] = "failed"
            error_tracker["page_load"]["error"] = "Page load timeout: Key elements (tweets or login) not found."
            print(f"[ERROR] Page load timed out. Current URL: {driver.current_url}, Title: {driver.title}")
            try:
                timeout_page_file = f"debug_timeout_{search_term.replace(' ', '_')}.html"
                with open(timeout_page_file, "w", encoding="utf-8") as f:
                    f.write(driver.page_source)
                print(f"[DEBUG] Saved page source on timeout to {timeout_page_file}")
            except Exception as ex_save:
                print(f"[ERROR] Could not save page source on timeout: {ex_save}")
            return []
        except Exception as e:
            error_tracker["page_load"]["status"] = "failed"
            error_tracker["page_load"]["error"] = str(e)
            print(f"[ERROR] Page load failed with exception: {str(e)}. URL: {driver.current_url}")
            return []

        tweets = []
        seen_tweet_ids = set() # Use a set for efficient lookup of processed tweet IDs
        last_height = driver.execute_script("return document.body.scrollHeight")
        scroll_attempts = 0
        max_scroll_attempts = 20 # Reduced slightly, adjust as needed
        consecutive_no_new_tweets_scrolls = 0
        max_consecutive_no_new_tweets = 4 # Be a bit more patient

        print("[SCRAPE] Starting to scroll and collect tweets...")
        error_tracker["page_scroll"]["status"] = "in_progress"

        while scroll_attempts < max_scroll_attempts:
            scroll_attempts += 1
            tweets_found_this_scroll_pass = 0
            try:
                # Scroll down
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                # Wait for new content to load, or for scroll to take effect
                time.sleep(random.uniform(2.5, 4.0)) # Randomized wait after scroll

                error_tracker["tweet_extraction"]["status"] = "in_progress"
                # XPaths are critical here and highly subject to change by Twitter.
                # Using @data-testid is generally more robust.
                articles = driver.find_elements(By.XPATH, "//article[@data-testid='tweet']")
                
                if not articles and scroll_attempts == 1: # No articles on first load after successful page_load
                    print("[WARNING] No tweet articles found immediately after page load. Checking page source.")
                    # This might indicate an empty search result or a different page structure.
                    # Saving HTML here can be useful.
                    first_load_no_articles_file = f"debug_no_articles_{search_term.replace(' ', '_')}.html"
                    with open(first_load_no_articles_file, "w", encoding="utf-8") as f:
                        f.write(driver.page_source)
                    print(f"[DEBUG] Saved page source (no articles) to {first_load_no_articles_file}")


                for article in articles:
                    tweet_data = {}
                    tweet_id = None
                    try:
                        # Try to get tweet ID from a status link within the article
                        # This is often the most reliable way.
                        status_links = article.find_elements(By.XPATH, ".//a[contains(@href, '/status/')]")
                        for link_el in status_links:
                            href = link_el.get_attribute('href')
                            if href and '/status/' in href:
                                potential_id = href.split('/status/')[-1].split('?')[0]
                                if potential_id.isdigit():
                                    tweet_id = potential_id
                                    break
                        if tweet_id and tweet_id in seen_tweet_ids:
                            continue # Already processed this tweet

                        tweet_data["id"] = tweet_id
                    except Exception as e_id:
                        # print(f"[DEBUG] Minor issue extracting tweet ID: {e_id}")
                        pass # Continue, will try to process without ID or with fallback

                    if not tweet_id: # Fallback if ID extraction from URL failed or to ensure uniqueness if ID is missing
                        # Use hash of content or a unique placeholder if ID is absolutely not findable
                        # For now, if ID is missing, we might get duplicates if content is identical.
                        # Or, skip if ID is crucial for your deduplication.
                        # Let's try to make a temporary ID from first few words of text if real ID fails
                        pass


                    # Extract tweet text
                    try:
                        text_elements = article.find_elements(By.XPATH, ".//div[@data-testid='tweetText']")
                        if text_elements:
                            tweet_data["text"] = text_elements[0].text
                        else: # Fallback
                            lang_divs = article.find_elements(By.XPATH, ".//div[@lang]")
                            if lang_divs: tweet_data["text"] = lang_divs[0].text
                            else: continue # Skip if no text
                    except NoSuchElementException: continue
                    except Exception as e_text:
                        # print(f"[DEBUG] Error extracting tweet text: {e_text}")
                        continue

                    # If no proper ID, create a fallback based on text hash to avoid some duplicates
                    if not tweet_id and "text" in tweet_data:
                        tweet_id = f"hash_{hash(tweet_data['text'][:50])}" # Temporary ID
                        if tweet_id in seen_tweet_ids:
                            continue
                        tweet_data["id"] = tweet_id


                    if not tweet_data.get("id"): # If still no ID after fallbacks
                        # print("[DEBUG] Skipping tweet due to missing ID after fallbacks.")
                        continue


                    # Extract username
                    try:
                        user_name_elements = article.find_elements(By.XPATH, ".//div[@data-testid='User-Name']//span[contains(text(), '@')]")
                        if user_name_elements:
                            tweet_data["username"] = user_name_elements[0].text # Typically "@username"
                        else: # Fallback
                            user_name_block = article.find_elements(By.XPATH, ".//div[@data-testid='User-Name']")
                            if user_name_block: tweet_data["username"] = user_name_block[0].text.split('\n')[0] # Display name
                            else: tweet_data["username"] = "unknown_user"
                    except Exception: tweet_data["username"] = "unknown_user_exception"

                    # Extract hashtags
                    try:
                        hashtag_links = article.find_elements(By.XPATH, ".//a[contains(@href, '/hashtag/')]")
                        tweet_data["hashtags"] = [link.text for link in hashtag_links if link.text.startswith('#')]
                    except Exception: tweet_data["hashtags"] = []

                    if "text" in tweet_data and tweet_data["text"].strip():
                        tweets.append(tweet_data)
                        seen_tweet_ids.add(tweet_data["id"])
                        tweets_found_this_scroll_pass += 1
                
                error_tracker["tweet_extraction"]["status"] = "success" # Mark attempt as success

                if tweets_found_this_scroll_pass > 0:
                    print(f"[SCRAPE] Scroll {scroll_attempts}: Found {tweets_found_this_scroll_pass} new tweets. Total: {len(tweets)}")
                    consecutive_no_new_tweets_scrolls = 0 # Reset counter
                else:
                    consecutive_no_new_tweets_scrolls += 1
                    print(f"[SCRAPE] Scroll {scroll_attempts}: No new tweets. Consecutive empty scrolls: {consecutive_no_new_tweets_scrolls}")

                if consecutive_no_new_tweets_scrolls >= max_consecutive_no_new_tweets:
                    print(f"[SCRAPE] Reached {max_consecutive_no_new_tweets} consecutive scrolls with no new tweets. Stopping.")
                    break

                # Check if scroll height has changed
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height and scroll_attempts > 1: # Check after the first scroll attempt
                    # If height hasn't changed for a while AND no new tweets, likely end of page
                    if consecutive_no_new_tweets_scrolls > 1: # Give it a chance
                         print(f"[SCRAPE] Scroll height ({new_height}) hasn't changed from last ({last_height}) and no new tweets. Likely end of content.")
                         break
                last_height = new_height

            except WebDriverException as e_scroll_wd:
                print(f"[ERROR] WebDriverException during scroll/extraction: {str(e_scroll_wd)}")
                error_tracker["page_scroll"]["status"] = "failed"
                error_tracker["page_scroll"]["error"] = str(e_scroll_wd)
                break # Critical error, stop
            except Exception as e_extract_generic:
                print(f"[ERROR] Generic error during scroll/extraction: {str(e_extract_generic)}")
                traceback.print_exc() # Print full traceback for generic errors
                error_tracker["tweet_extraction"]["status"] = "partial"
                error_tracker["tweet_extraction"]["error"] = str(e_extract_generic)
                # Optionally break or continue depending on severity
                consecutive_no_new_tweets_scrolls +=1 # Count as an empty scroll if extraction fails badly

        error_tracker["page_scroll"]["status"] = "success" if scroll_attempts > 0 else "skipped"
        print(f"[SCRAPE] Scraping phase complete. Found {len(tweets)} potential tweets from {scroll_attempts} scroll attempts.")

        # Save final HTML for debugging
        try:
            # Note: file_operations status will be updated by YAML saving. This is just for debug HTML.
            final_html_file = f"debug_final_page_{search_term.replace(' ', '_')}.html"
            with open(final_html_file, "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            print(f"[DEBUG] Saved final page HTML to {final_html_file}")
        except Exception as e_save_final:
            print(f"[ERROR] Failed to save final debug HTML: {str(e_save_final)}")

    except Exception as e_critical:
        print(f"[CRITICAL] Unexpected error in scrape_twitter_trends: {str(e_critical)}")
        traceback.print_exc()
        for step_key in ["driver_setup", "page_load", "page_scroll", "tweet_extraction"]:
            if error_tracker.get(step_key, {}).get("status") == "in_progress":
                error_tracker[step_key]["status"] = "failed"
                error_tracker[step_key]["error"] = f"Aborted due to critical error: {e_critical}"
        return []
    finally:
        if driver:
            try:
                driver.quit()
                print("[CLEANUP] WebDriver closed successfully")
            except Exception as e_quit:
                print(f"[WARNING] Error closing WebDriver: {str(e_quit)}")
    
    # Final deduplication based on text content (your original logic, good as a final pass)
    if not tweets:
        error_tracker["deduplication"]["status"] = "skipped"
        error_tracker["deduplication"]["error"] = "No tweets collected to deduplicate"
        return []

    try:
        error_tracker["deduplication"]["status"] = "in_progress"
        unique_tweets_final = []
        seen_texts_final = set()
        for tweet in tweets:
            text_content = tweet.get("text", "").strip().lower() # Normalize for deduplication
            if text_content and text_content not in seen_texts_final:
                seen_texts_final.add(text_content)
                unique_tweets_final.append(tweet)
        
        if len(tweets) != len(unique_tweets_final):
            print(f"[DEDUPE] Final text-based deduplication: {len(tweets)} -> {len(unique_tweets_final)} tweets")
        else:
            print(f"[DEDUPE] Final text-based deduplication: No further duplicates found by text from {len(tweets)} tweets.")
        error_tracker["deduplication"]["status"] = "success"
        return unique_tweets_final
    except Exception as e_dedupe_final:
        print(f"[ERROR] Final deduplication error: {str(e_dedupe_final)}")
        error_tracker["deduplication"]["status"] = "failed"
        error_tracker["deduplication"]["error"] = str(e_dedupe_final)
        return tweets # Return original list if final dedupe fails

# ... (rest of your functions: calculate_relevancy_score, remove_duplicates (which is now integrated), save_to_yaml, display_by_segments, analyze_twitter_trend, __main__)
# Ensure `remove_duplicates` is either called or its logic is fully integrated.
# The `scrape_twitter_trends` now does ID-based deduplication during scraping and text-based at the end.
# The original `remove_duplicates` function might be redundant if the final pass in `scrape_twitter_trends` is sufficient.
# For now, I'll assume the user might still want the separate `remove_duplicates` call or will adapt.
# The `analyze_twitter_trend` function calls `remove_duplicates` *after* `scrape_twitter_trends`.
# The current `scrape_twitter_trends` function already returns deduplicated (by ID, then by text) tweets.
# So, the `remove_duplicates` call in `analyze_twitter_trend` might become redundant if this new version is used.

def calculate_relevancy_score(tweets: list, search_term: str) -> tuple:
    # (Your existing calculate_relevancy_score function - seems okay for its purpose)
    # ...
    error_tracker["nlp_processing"]["status"] = "in_progress"
    
    if not tweets:
        print("[WARNING] No tweets to process for relevancy scoring.")
        error_tracker["nlp_processing"]["status"] = "skipped"
        error_tracker["nlp_processing"]["error"] = "No tweets to process"
        return [], 0
    
    try:
        print("[NLP] Initializing NLTK stopwords...") # Changed message slightly
        # Ensure NLTK data is downloaded. You might want a more robust download mechanism
        # or instruct users to download it manually once.
        try:
            nltk.data.find('corpora/stopwords')
        except nltk.downloader.DownloadError:
            print("[NLP] Downloading NLTK stopwords resource...")
            nltk.download("stopwords", quiet=False) # Set quiet=False to see download progress/errors
        except Exception as e_nltk_find: # Catch other potential errors with find
            print(f"[NLP_ERROR] Could not verify NLTK stopwords: {e_nltk_find}. Attempting download anyway.")
            nltk.download("stopwords", quiet=False)

        stop_words = set(stopwords.words("english"))

        texts = [t.get("text", "") for t in tweets if t.get("text")]
        if not texts:
            print("[WARNING] No valid tweet texts for NLP processing.")
            error_tracker["nlp_processing"]["status"] = "skipped"
            error_tracker["nlp_processing"]["error"] = "No valid tweet texts"
            # Return original tweets with a default score if no text for NLP
            for tweet in tweets:
                if "relevancy_score" not in tweet: tweet["relevancy_score"] = 0
            return tweets, 0
            
        all_docs = [search_term] + texts
        
        if len(set(all_docs)) <= 1 and len(all_docs) > 1 : # Check if all docs are identical but there's more than one
            print("[WARNING] All documents (search term and tweets) are identical or too few unique texts for meaningful TF-IDF analysis.")
            # Assign a score based on whether the tweet text *is* the search term (highly relevant) or not.
            # This is a simple heuristic.
            mean_score_val = 0
            num_scored = 0
            for i, tweet_text in enumerate(texts):
                if tweet_text.strip().lower() == search_term.strip().lower():
                    tweets[i]["relevancy_score"] = 100
                else:
                    # If search term is a substring of tweet text, give some points
                    # This is a simple heuristic.
                    tweets[i]["relevancy_score"] = 75 if search_term.strip().lower() in tweet_text.strip().lower() else 25
                mean_score_val += tweets[i]["relevancy_score"]
                num_scored +=1
            
            trend_score = int(mean_score_val / num_scored) if num_scored > 0 else 0
            error_tracker["nlp_processing"]["status"] = "partial"
            error_tracker["nlp_processing"]["error"] = "Not enough unique content for TF-IDF; used heuristic scoring."
            return tweets, trend_score
        elif len(all_docs) <=1: # Only search term, no tweets with text
             print("[WARNING] No tweet texts to compare with search term.")
             error_tracker["nlp_processing"]["status"] = "skipped"
             error_tracker["nlp_processing"]["error"] = "No tweet texts for TF-IDF."
             return tweets, 0


        print("[NLP] Calculating TF-IDF vectors...")
        vectorizer = TfidfVectorizer(stop_words=list(stop_words)) # Pass as list
        tfidf = vectorizer.fit_transform(all_docs)

        print("[NLP] Computing relevancy scores (cosine similarity)...")
        # Similarity between search_term (tfidf[0]) and all tweet texts (tfidf[1:])
        sim_scores = cosine_similarity(tfidf[0:1], tfidf[1:]).flatten()
        
        for i, score in enumerate(sim_scores):
            # Ensure index i is valid for tweets list (it should be if texts and tweets correspond)
            if i < len(tweets):
                 tweets[i]["relevancy_score"] = int(score * 100)
            # else: # Should not happen if texts are derived correctly from tweets
                 # print(f"[NLP_WARNING] Mismatch between sim_scores length ({len(sim_scores)}) and tweets with text ({len(texts)}). Score index {i} out of bounds.")

        trend_score = int(sim_scores.mean() * 100) if len(sim_scores) > 0 else 0
        
        print(f"[NLP] Relevancy calculation complete. Overall trend score: {trend_score}")
        error_tracker["nlp_processing"]["status"] = "success"
        return tweets, trend_score
    except Exception as e:
        print(f"[ERROR] Error in relevancy calculation: {str(e)}")
        traceback.print_exc()
        error_tracker["nlp_processing"]["status"] = "failed"
        error_tracker["nlp_processing"]["error"] = str(e)
        
        for tweet in tweets: # Assign default score on failure
            if "relevancy_score" not in tweet: tweet["relevancy_score"] = 0
        return tweets, 0


# remove_duplicates function might be redundant now, as deduplication is part of scrape_twitter_trends
# def remove_duplicates(tweets: list) -> list: ...

def save_to_yaml(data: dict, filename: str) -> bool:
    # (Your existing save_to_yaml function - seems okay)
    # ...
    # Make sure "file_operations" in error_tracker is correctly managed if multiple file ops occur
    current_op_status = "in_progress" # Reset for this specific operation
    current_op_error = None
    try:
        # error_tracker["file_operations"]["status"] = "in_progress" # This might overwrite other file ops
        with open(filename, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
        print(f"[FILE] Successfully saved data to {filename}")
        current_op_status = "success"
        # Update global tracker carefully if this is the primary file op for the step
        if "results.yaml" in filename or "raw.yaml" in filename : # Heuristic for main data files
             error_tracker["file_operations"]["status"] = "success"
        return True
    except Exception as e:
        print(f"[ERROR] Failed to save to {filename}: {str(e)}")
        current_op_status = "failed"
        current_op_error = str(e)
        if "results.yaml" in filename or "raw.yaml" in filename :
            error_tracker["file_operations"]["status"] = "failed"
            error_tracker["file_operations"]["error"] = str(e)
        return False


def display_by_segments(tweets: list) -> None:
    # (Your existing display_by_segments function - seems okay)
    # ...
    segments = {
        "High (>=75)":    lambda t: t.get("relevancy_score", 0) >= 75,
        "Medium (50–74)": lambda t: 50 <= t.get("relevancy_score", 0) < 75,
        "Low (<50)":      lambda t: t.get("relevancy_score", 0) < 50,
    }
    
    print("\n[RESULTS] Tweets by relevancy segments:")
    any_tweets_displayed = False
    for title, cond_func in segments.items(): # Use cond_func
        # Filter tweets that have 'relevancy_score' and meet condition
        group = [t for t in tweets if "relevancy_score" in t and cond_func(t)]
        if not group:
            continue
        any_tweets_displayed = True
        print(f"\n=== {title} Relevancy ===")
        for t in group:
            # Ensure 'username' and 'text' keys exist, provide defaults if not
            username = t.get('username', 'unknown_user')
            text_content = t.get('text', '')
            score = t.get('relevancy_score', 0)
            
            display_text = f"[{score:>3}] {username}: {text_content[:100]}..." if len(text_content) > 100 else f"[{score:>3}] {username}: {text_content}"
            print(display_text)
    if not any_tweets_displayed and tweets: # Some tweets exist but none fit segments (e.g. all 0 score)
        print("\nNo tweets fit into the defined relevancy segments (High/Medium/Low). Displaying all tweets with scores:")
        for t in tweets:
            username = t.get('username', 'unknown_user')
            text_content = t.get('text', '')
            score = t.get('relevancy_score', 0)
            display_text = f"[{score:>3}] {username}: {text_content[:100]}..." if len(text_content) > 100 else f"[{score:>3}] {username}: {text_content}"
            print(display_text)
    elif not tweets:
        print("\nNo tweets to display.")


def analyze_twitter_trend(search_term: str,
                          save_raw: bool = True,
                          save_scored: bool = True) -> dict:
    """
    Main pipeline: scrape -> dedupe (integrated) -> score -> save -> display.
    Returns a dict {'trend_relevancy': int, 'tweets': list}.
    """
    # Reset error tracker at the start of each analysis
    for step in error_tracker: # Global error_tracker
        error_tracker[step] = {"status": "not_started", "error": None}
        
    print(f"\n[START] Analyzing Twitter trend for: '{search_term}'")
    print("[INFO] This may take a few minutes. Please wait...\n")
    
    raw_tweets = [] # Initialize
    final_tweets = [] # Initialize
    trend_score = 0 # Initialize

    try:
        # 1) Scrape (includes initial deduplication by ID and final by text)
        print("[STEP 1/5] Scraping and initial deduplicating tweets...")
        raw_tweets = scrape_twitter_trends(search_term) # This now returns more deduplicated tweets
        print(f"[INFO] Scraping complete. Effective unique tweets found: {len(raw_tweets)}")
        
        if not raw_tweets:
            print("[ERROR] No tweets found or scraping failed for the given search term.")
            # Error summary will be printed in finally block
            return {"trend_relevancy": 0, "tweets": []}

        # The `remove_duplicates` call here might be redundant if `scrape_twitter_trends`
        # already does comprehensive deduplication. For now, let's assume `scrape_twitter_trends`
        # handles it. If you had a separate `remove_duplicates` function, you'd call it here.
        # Current `scrape_twitter_trends` includes a final text-based dedupe.
        unique_tweets = raw_tweets # `raw_tweets` from the updated scraper should be well-deduplicated

        # 2) Optional: Save raw (now unique)
        if save_raw:
            print("[STEP 2/5] Saving unique raw tweets...")
            raw_fn = f"{search_term.replace(' ', '_')}_raw_unique.yaml" # Indicate they are unique
            # Pass only the tweets list to save_to_yaml if that's its expectation
            if save_to_yaml({"search_term": search_term, "raw_tweets_count": len(unique_tweets), "tweets": unique_tweets}, raw_fn):
                print(f"[INFO] Unique raw tweets saved to {raw_fn}")
            # error_tracker['file_operations'] will be updated by save_to_yaml

        # 3) Score
        print("[STEP 3/5] Calculating relevancy scores...")
        scored_tweets, trend_score = calculate_relevancy_score(unique_tweets, search_term)

        # 4) Sort descending
        print("[STEP 4/5] Sorting tweets by relevancy...")
        final_tweets = sorted(scored_tweets,
                              key=lambda x: x.get("relevancy_score", 0),
                              reverse=True)

        # 5) Optional: Save scored
        if save_scored:
            print("[STEP 5/5] Saving scored results...")
            out = {"trend_relevancy": trend_score, "search_term": search_term, "tweets_count": len(final_tweets), "tweets": final_tweets}
            out_fn = f"{search_term.replace(' ', '_')}_results.yaml"
            if save_to_yaml(out, out_fn):
                print(f"[INFO] Scored results saved to {out_fn}")
            # error_tracker['file_operations'] will be updated by save_to_yaml


        # Display on console (moved out of numbered steps, as it's a final action)
        print("\n[DISPLAY] Displaying results on console...")
        display_by_segments(final_tweets)

        return {"trend_relevancy": trend_score, "tweets": final_tweets}
    
    except Exception as e:
        print(f"[CRITICAL] Error in main analysis pipeline: {str(e)}")
        traceback.print_exc()
        # Ensure error tracker reflects this critical failure if not caught by specific steps
        # For example, if error is between steps.
        return {"trend_relevancy": trend_score, "tweets": final_tweets} # Return what we have
    finally:
        print("\n[SUMMARY] Error tracking report:")
        has_error = False
        root_cause_step = None
        root_cause_error = None

        # Define typical pipeline order for finding root cause
        pipeline_order = ["driver_setup", "page_load", "page_scroll", "tweet_extraction", "deduplication", "nlp_processing", "file_operations"]
        
        for step in pipeline_order:
            status_info = error_tracker.get(step) # Use .get for safety
            if not status_info: # Should not happen if error_tracker is well-maintained
                print(f"  ❓ {step}: Status not recorded.")
                continue

            if status_info["status"] == "failed":
                has_error = True
                print(f"  ❌ {step}: {status_info['error']}")
                if not root_cause_step: # Capture the first failure in the pipeline as root cause
                    root_cause_step = step
                    root_cause_error = status_info['error']
            elif status_info["status"] == "partial":
                print(f"  ⚠️ {step}: {status_info['error']}")
            elif status_info["status"] == "success":
                print(f"  ✅ {step}: Completed successfully")
            elif status_info["status"] == "skipped":
                print(f"  ⏭️ {step}: Skipped - {status_info.get('error', 'No specific reason')}")
            elif status_info["status"] == "not_started":
                 print(f"  ⚪ {step}: Not started")
            else: # Unknown status
                print(f"  ❓ {step}: Status '{status_info['status']}' - {status_info.get('error', 'Details unknown')}")
                
        if root_cause_step:
            print(f"\n[ROOT CAUSE ANALYSIS] The primary failure likely occurred in the '{root_cause_step}' step.")
            print(f"  Error message: {root_cause_error}")
            if root_cause_step != pipeline_order[-1]: # If not the last step
                 print("  This may have impacted subsequent steps.")
        elif has_error and not root_cause_step:
            print("\n[ROOT CAUSE ANALYSIS] Errors occurred, but a specific root cause step in the main pipeline was not identified from the first failure.")


if __name__ == "__main__":
    try:
        print("Twitter Trend Analysis Tool")
        print("==========================")
        
        term = select_random_search_term()
        
        start_time = time.time()
        results = analyze_twitter_trend(term)
        elapsed_time = time.time() - start_time
        
        if results and results.get("tweets"):
            print(f"\n[COMPLETE] Analysis for '{term}' completed in {elapsed_time:.1f} seconds.")
            print(f"[RESULTS] Overall trend relevancy score: {results['trend_relevancy']}/100")
            print(f"[RESULTS] Found {len(results['tweets'])} relevant tweets.")
        else:
            print(f"\n[FAILURE] No relevant results found for '{term}'. Check logs for errors.")
            # The 'finally' block in analyze_twitter_trend will print the error summary.
    except KeyboardInterrupt:
        print("\n[ABORT] Operation cancelled by user.")
    except Exception as e:
        print(f"\n[CRITICAL] An unexpected error occurred in __main__: {str(e)}")
        traceback.print_exc()
