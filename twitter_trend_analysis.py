"""
Twitter Trend Analysis Bot

Project Overview:
    A Python-based tool that analyzes Twitter trends without API access,
    providing relevancy scores for posts related to searched topics.

Objectives:
  - Create a trend analysis system without using the official Twitter API
  - Implement a relevancy scoring algorithm (0–100) for posts
  - Filter out irrelevant content in search results
  - Prevent duplicate results in the output

Environment Requirements (requirements.txt):
  selenium==4.9.1
  beautifulsoup4==4.12.2
  PyYAML==6.0
  nltk==3.8.1
  scikit-learn==1.2.2
  webdriver-manager==3.8.6

Usage:
    python twitter_trend_analysis.py
"""

import time
import random
import traceback
from bs4 import BeautifulSoup
import yaml
import nltk
from nltk.corpus import stopwords
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException, TimeoutException, NoSuchElementException

# Error tracking dictionary to identify the root cause of failures
error_tracker = {
    "driver_setup": {"status": "not_started", "error": None},
    "page_load": {"status": "not_started", "error": None},
    "page_scroll": {"status": "not_started", "error": None},
    "tweet_extraction": {"status": "not_started", "error": None},
    "nlp_processing": {"status": "not_started", "error": None},
    "deduplication": {"status": "not_started", "error": None},
    "file_operations": {"status": "not_started", "error": None},
}

# Dictionary of search terms by category for automatic selection
SEARCH_TERMS = {
    "technology": ["AI", "Machine Learning", "Blockchain", "Python Programming", "Cloud Computing", "Data Science"],
    "entertainment": ["Netflix", "Marvel", "Taylor Swift", "Movie Releases", "Gaming News"],
    "news": ["Breaking News", "Climate Change", "Politics", "World Events", "COVID Updates"],
    "sports": ["NBA", "Soccer", "Tennis", "Olympics", "Formula 1"],
    "business": ["Startup Funding", "Stock Market", "Entrepreneurship", "Business Strategy", "Crypto"]
}

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
    try:
        error_tracker["driver_setup"]["status"] = "in_progress"
        print(f"[SETUP] Initializing Chrome WebDriver...")
        chrome_driver_path = r"C:\Users\incre\Downloads\chromedriver-win64\chromedriver-win64\chromedriver.exe"

        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Run in headless mode
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")  # Overcome limited resource problems
        chrome_options.add_argument("--lang=en")  # Force English language
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36")  # Set a common user agent
        
        try:
            service = Service(executable_path=chrome_driver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            error_tracker["driver_setup"]["status"] = "success"
        except WebDriverException as e:
            error_tracker["driver_setup"]["status"] = "failed"
            error_tracker["driver_setup"]["error"] = str(e)
            print(f"[ERROR] Chrome WebDriver setup failed: {str(e)}")
            return []

        # Twitter often requires a larger viewport to display content properly
        driver.set_window_size(1920, 1080)
        
        error_tracker["page_load"]["status"] = "in_progress"
        url = f"https://twitter.com/search?q={search_term}&src=typed_query&f=live"  # Adding &f=live for recent tweets
        print(f"[NETWORK] Accessing URL: {url}")
        
        try:
            driver.get(url)
            # Wait for page to load initially
            time.sleep(30)  # Adjusted wait time for initial load
            
            # Check if we got the page
            if "twitter" not in driver.current_url.lower():
                error_tracker["page_load"]["status"] = "failed"
                error_tracker["page_load"]["error"] = "Redirected away from Twitter"
                print("[ERROR] Page load failed: Redirected away from Twitter")
                return []
                
            error_tracker["page_load"]["status"] = "success"
        except TimeoutException as e:
            error_tracker["page_load"]["status"] = "failed"
            error_tracker["page_load"]["error"] = "Page load timeout"
            print(f"[ERROR] Page load timed out: {str(e)}")
            return []
        except Exception as e:
            error_tracker["page_load"]["status"] = "failed"
            error_tracker["page_load"]["error"] = str(e)
            print(f"[ERROR] Page load failed: {str(e)}")
            return []
        
        # Check if we're on a login page or access is restricted
        if "log in" in driver.title.lower() or any(x in driver.page_source.lower() for x in ["sign up", "log in to twitter"]):
            print("[WARNING] Twitter may be requiring login. Limited results expected.")
        
        tweets = []
        last_height = driver.execute_script("return document.body.scrollHeight")
        scroll_attempts = 0
        max_attempts = 25
        consecutive_empty_scrolls = 0
        max_empty_scrolls = 3
        
        print("[SCRAPE] Starting to scroll and collect tweets...")
        error_tracker["page_scroll"]["status"] = "in_progress"
        
        while scroll_attempts < max_attempts:
            try:
                # Scroll down
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(3)  # Adjusted wait time
                
                # Get new tweets before checking height
                error_tracker["tweet_extraction"]["status"] = "in_progress"
                try:
                    # Try multiple selectors to find tweets
                    all_articles = driver.find_elements("xpath", "//article")
                    
                    if all_articles:
                        print(f"[SCRAPE] Found {len(all_articles)} articles in scroll {scroll_attempts+1}")
                        tweets_before = len(tweets)
                        
                        for article in all_articles:
                            tweet_data = {}
                            
                            # Extract tweet ID to avoid duplicates
                            try:
                                article_html = article.get_attribute('outerHTML')
                                tweet_id = None
                                if 'data-testid="tweet"' in article_html:
                                    # Try to extract tweet ID from various attributes
                                    for attr in ['data-tweet-id', 'data-item-id']:
                                        if attr in article_html:
                                            tweet_id = article_html.split(attr+'="')[1].split('"')[0]
                                            break
                                
                                if tweet_id and any(t.get("id") == tweet_id for t in tweets):
                                    continue  # Skip already processed tweets
                                    
                                tweet_data["id"] = tweet_id
                            except Exception as e:
                                print(f"[WARNING] Couldn't extract tweet ID: {str(e)}")
                                pass  # Continue even if we can't get the ID
                            
                            # Get tweet text
                            try:
                                # Try multiple selectors for tweet text
                                text_elements = article.find_elements("xpath", ".//div[@lang]")
                                if text_elements:
                                    tweet_data["text"] = text_elements[0].text
                                else:
                                    text_elements = article.find_elements("xpath", ".//div[@data-testid='tweetText']")
                                    if text_elements:
                                        tweet_data["text"] = text_elements[0].text
                                    else:
                                        continue  # Skip if no text found
                            except NoSuchElementException:
                                print("[WARNING] Tweet text element not found, trying alternative selectors")
                                continue
                            except Exception as e:
                                print(f"[WARNING] Error extracting tweet text: {str(e)}")
                                continue
                            
                            # Get username
                            try:
                                username_elements = article.find_elements("xpath", ".//div[@data-testid='User-Name']")
                                if username_elements:
                                    tweet_data["username"] = username_elements[0].text.split('\n')[0]
                                else:
                                    tweet_data["username"] = "unknown"
                            except Exception as e:
                                print(f"[WARNING] Error extracting username: {str(e)}")
                                tweet_data["username"] = "unknown"
                            
                            # Get hashtags
                            try:
                                hashtag_links = article.find_elements("xpath", ".//a[contains(@href, '/hashtag/')]")
                                tweet_data["hashtags"] = [link.text for link in hashtag_links if link.text.startswith('#')]
                            except Exception as e:
                                print(f"[WARNING] Error extracting hashtags: {str(e)}")
                                tweet_data["hashtags"] = []
                            
                            if "text" in tweet_data and tweet_data["text"].strip():
                                tweets.append(tweet_data)
                        
                        # Check if we got new tweets
                        if len(tweets) == tweets_before:
                            consecutive_empty_scrolls += 1
                            print(f"[SCRAPE] No new tweets in scroll {scroll_attempts+1}, empty count: {consecutive_empty_scrolls}")
                        else:
                            consecutive_empty_scrolls = 0
                    else:
                        consecutive_empty_scrolls += 1
                        print(f"[WARNING] No articles found in scroll {scroll_attempts+1}, empty count: {consecutive_empty_scrolls}")
                    
                    error_tracker["tweet_extraction"]["status"] = "success"
                except Exception as e:
                    print(f"[ERROR] Error while parsing tweets: {str(e)}")
                    error_tracker["tweet_extraction"]["status"] = "partial"
                    error_tracker["tweet_extraction"]["error"] = str(e)
                
                # Check if scrolled to bottom or no new content
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height or consecutive_empty_scrolls >= max_empty_scrolls:
                    print(f"[SCRAPE] Reached bottom or no new tweets after {consecutive_empty_scrolls} attempts")
                    break
                
                last_height = new_height
                scroll_attempts += 1
                print(f"[PROGRESS] Completed scroll {scroll_attempts}/{max_attempts}, found {len(tweets)} tweets so far")
            
            except Exception as e:
                print(f"[ERROR] Scroll operation failed: {str(e)}")
                error_tracker["page_scroll"]["status"] = "failed"
                error_tracker["page_scroll"]["error"] = str(e)
                break
        
        if scroll_attempts > 0:
            error_tracker["page_scroll"]["status"] = "success"

        print(f"[SCRAPE] Scraping complete. Found {len(tweets)} tweets.")
        
        # Save HTML for debugging
        try:
            error_tracker["file_operations"]["status"] = "in_progress"
            html = driver.page_source
            debug_file = f"debug_{search_term.replace(' ', '_')}.html"
            with open(debug_file, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"[DEBUG] Saved HTML to {debug_file}")
            error_tracker["file_operations"]["status"] = "success"
        except Exception as e:
            print(f"[ERROR] Failed to save debug HTML: {str(e)}")
            error_tracker["file_operations"]["status"] = "failed"
            error_tracker["file_operations"]["error"] = str(e)

    except Exception as e:
        print(f"[CRITICAL] Unexpected error during scraping: {str(e)}")
        traceback.print_exc()
        # Determine which step failed based on the error tracking
        for step, status in error_tracker.items():
            if status["status"] == "in_progress" or status["status"] == "not_started":
                error_tracker[step]["status"] = "failed"
                error_tracker[step]["error"] = "Aborted due to critical error"
        return []
    finally:
        if driver:
            try:
                driver.quit()
                print("[CLEANUP] WebDriver closed successfully")
            except Exception as e:
                print(f"[WARNING] Error closing WebDriver: {str(e)}")
    
    # Final check to remove any remaining duplicates
    try:
        error_tracker["deduplication"]["status"] = "in_progress"
        unique_tweets = []
        seen_texts = set()
        
        for tweet in tweets:
            text = tweet.get("text", "").strip()
            if text and text not in seen_texts:
                seen_texts.add(text)
                unique_tweets.append(tweet)
        
        print(f"[DEDUPE] Initial deduplication: {len(tweets)} → {len(unique_tweets)} tweets")
        error_tracker["deduplication"]["status"] = "success"
        return unique_tweets
    except Exception as e:
        print(f"[ERROR] Deduplication error: {str(e)}")
        error_tracker["deduplication"]["status"] = "failed"
        error_tracker["deduplication"]["error"] = str(e)
        return tweets

def calculate_relevancy_score(tweets: list, search_term: str) -> tuple:
    """
    Calculate relevancy scores for each tweet based on cosine similarity.
    Returns a tuple of (scored_tweets, overall_trend_score).
    """
    error_tracker["nlp_processing"]["status"] = "in_progress"
    
    if not tweets:
        print("[WARNING] No tweets to process for relevancy scoring.")
        error_tracker["nlp_processing"]["status"] = "skipped"
        error_tracker["nlp_processing"]["error"] = "No tweets to process"
        return [], 0
    
    try:
        print("[NLP] Downloading NLTK stopwords...")
        nltk.download("stopwords", quiet=True)
        stop_words = set(stopwords.words("english"))

        texts = [t.get("text", "") for t in tweets if t.get("text")]
        if not texts:
            print("[WARNING] No valid tweet texts for processing.")
            error_tracker["nlp_processing"]["status"] = "skipped"
            error_tracker["nlp_processing"]["error"] = "No valid tweet texts"
            return tweets, 0
            
        all_docs = [search_term] + texts
        
        # Handle very short or identical documents
        if len(set(all_docs)) <= 1:
            print("[WARNING] Not enough unique content for meaningful analysis.")
            for tweet in tweets:
                tweet["relevancy_score"] = 50  # Assign neutral score
            error_tracker["nlp_processing"]["status"] = "partial"
            error_tracker["nlp_processing"]["error"] = "Not enough unique content"
            return tweets, 50

        print("[NLP] Calculating TF-IDF vectors...")
        vectorizer = TfidfVectorizer(stop_words=stop_words)
        tfidf = vectorizer.fit_transform(all_docs)

        print("[NLP] Computing relevancy scores...")
        sim_scores = cosine_similarity(tfidf[0:1], tfidf[1:]).flatten()
        for i, score in enumerate(sim_scores):
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
        
        # Assign default scores in case of failure
        for tweet in tweets:
            tweet["relevancy_score"] = 0
        return tweets, 0

def remove_duplicates(tweets: list) -> list:
    """
    Remove duplicate tweets based on the hash of the tweet text.
    """
    try:
        error_tracker["deduplication"]["status"] = "in_progress"
        seen = set()
        unique = []
        for t in tweets:
            if "text" not in t or not t["text"]:
                continue
                
            h = hash(t["text"])
            if h not in seen:
                seen.add(h)
                unique.append(t)
        
        print(f"[DEDUPE] Final deduplication: {len(tweets)} → {len(unique)} tweets")
        error_tracker["deduplication"]["status"] = "success"
        return unique
    except Exception as e:
        print(f"[ERROR] Error during final deduplication: {str(e)}")
        error_tracker["deduplication"]["status"] = "failed"
        error_tracker["deduplication"]["error"] = str(e)
        return tweets

def save_to_yaml(data: dict, filename: str) -> bool:
    """
    Dump the given data dict to a YAML file.
    Return True if successful, False otherwise.
    """
    try:
        error_tracker["file_operations"]["status"] = "in_progress"
        with open(filename, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
        print(f"[FILE] Successfully saved data to {filename}")
        error_tracker["file_operations"]["status"] = "success"
        return True
    except Exception as e:
        print(f"[ERROR] Failed to save to {filename}: {str(e)}")
        error_tracker["file_operations"]["status"] = "failed"
        error_tracker["file_operations"]["error"] = str(e)
        return False

def display_by_segments(tweets: list) -> None:
    """
    Print tweets grouped by relevancy:
      - High: >=75
      - Medium: 50–74
      - Low: <50
    """
    segments = {
        "High (>=75)":    lambda t: t["relevancy_score"] >= 75,
        "Medium (50–74)": lambda t: 50 <= t["relevancy_score"] < 75,
        "Low (<50)":      lambda t: t["relevancy_score"] < 50,
    }
    
    print("\n[RESULTS] Tweets by relevancy segments:")
    for title, cond in segments.items():
        group = [t for t in tweets if cond(t)]
        if not group:
            continue
        print(f"\n=== {title} Relevancy ===")
        for t in group:
            print(f"[{t['relevancy_score']:>3}] {t['username']}: {t['text'][:100]}..." if len(t['text']) > 100 else f"[{t['relevancy_score']:>3}] {t['username']}: {t['text']}")

def analyze_twitter_trend(search_term: str,
                          save_raw: bool = True,
                          save_scored: bool = True) -> dict:
    """
    Main pipeline: scrape → dedupe → score → save → display.
    Returns a dict {'trend_relevancy': int, 'tweets': list}.
    """
    # Reset error tracker at the start of each analysis
    for step in error_tracker:
        error_tracker[step] = {"status": "not_started", "error": None}
        
    print(f"\n[START] Analyzing Twitter trend for: '{search_term}'")
    print("[INFO] This may take a few minutes. Please wait...\n")
    
    try:
        # 1) Scrape
        print("[STEP 1/7] Scraping tweets...")
        raw_tweets = scrape_twitter_trends(search_term)
        print(f"[INFO] Scraped tweets: {len(raw_tweets)}")
        
        if not raw_tweets:
            print("[ERROR] No tweets found for the given search term.")
            return {"trend_relevancy": 0, "tweets": []}

        # 2) Deduplicate
        print("[STEP 2/7] Removing duplicate tweets...")
        unique_tweets = remove_duplicates(raw_tweets)
        print(f"[INFO] Unique tweets after deduplication: {len(unique_tweets)}")
        
        if not unique_tweets:
            print("[ERROR] No unique tweets found after deduplication.")
            return {"trend_relevancy": 0, "tweets": []}

        # 3) Optional: Save raw
        if save_raw:
            print("[STEP 3/7] Saving raw tweets...")
            raw_fn = f"{search_term.replace(' ', '_')}_raw.yaml"
            if save_to_yaml({"raw_tweets": unique_tweets}, raw_fn):
                print(f"[INFO] Raw tweets saved to {raw_fn}")

        # 4) Score
        print("[STEP 4/7] Calculating relevancy scores...")
        scored_tweets, trend_score = calculate_relevancy_score(unique_tweets, search_term)

        # 5) Sort descending
        print("[STEP 5/7] Sorting tweets by relevancy...")
        sorted_tweets = sorted(scored_tweets,
                              key=lambda x: x.get("relevancy_score", 0),
                              reverse=True)

        # 6) Optional: Save scored
        if save_scored:
            print("[STEP 6/7] Saving scored results...")
            out = {"trend_relevancy": trend_score, "tweets": sorted_tweets}
            out_fn = f"{search_term.replace(' ', '_')}_results.yaml"
            if save_to_yaml(out, out_fn):
                print(f"[INFO] Scored results saved to {out_fn}")

        # 7) Display on console
        print("[STEP 7/7] Displaying results...")
        display_by_segments(sorted_tweets)

        return {"trend_relevancy": trend_score, "tweets": sorted_tweets}
    
    except Exception as e:
        print(f"[CRITICAL] Error in analysis pipeline: {str(e)}")
        traceback.print_exc()
        return {"trend_relevancy": 0, "tweets": []}
    finally:
        # Print error summary
        print("\n[SUMMARY] Error tracking report:")
        has_error = False
        for step, status in error_tracker.items():
            if status["status"] == "failed":
                has_error = True
                print(f"  ❌ {step}: {status['error']}")
            elif status["status"] == "partial":
                print(f"  ⚠️ {step}: {status['error']}")
            elif status["status"] == "success":
                print(f"  ✅ {step}: Completed successfully")
            elif status["status"] == "skipped":
                print(f"  ⏭️ {step}: {status['error']}")
            else:
                print(f"  ❓ {step}: Status unknown")
                
        if has_error:
            # Find the root cause - first failure in the pipeline
            root_cause = None
            for step, status in error_tracker.items():
                if status["status"] == "failed":
                    root_cause = step
                    break
                    
            if root_cause:
                print(f"\n[ROOT CAUSE] The primary failure occurred in the '{root_cause}' step:")
                print(f"  Error message: {error_tracker[root_cause]['error']}")
                print("  This error likely triggered subsequent failures in the pipeline.")

if __name__ == "__main__":
    try:
        print("Twitter Trend Analysis Tool")
        print("==========================")
        
        # Use the automatic search term selection instead of user input
        term = select_random_search_term()
        
        start_time = time.time()
        results = analyze_twitter_trend(term)
        elapsed_time = time.time() - start_time
        
        if results and results.get("tweets"):
            print(f"\n[COMPLETE] Analysis completed in {elapsed_time:.1f} seconds.")
            print(f"[RESULTS] Overall trend relevancy score: {results['trend_relevancy']}/100")
            print(f"[RESULTS] Found {len(results['tweets'])} relevant tweets.")
        else:
            print("\n[FAILURE] No relevant results found. Try a different search term or check your internet connection.")
    except KeyboardInterrupt:
        print("\n[ABORT] Operation cancelled by user.")
    except Exception as e:
        print(f"\n[CRITICAL] An unexpected error occurred: {str(e)}")
        traceback.print_exc()