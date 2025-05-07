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
from bs4 import BeautifulSoup
import yaml
import nltk
from nltk.corpus import stopwords
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

def scrape_twitter_trends(search_term: str) -> list:
    chrome_driver_path = r"C:\Users\incre\Downloads\chromedriver-win64\chromedriver-win64\chromedriver.exe"

    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Run in headless mode
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")  # Overcome limited resource problems
    chrome_options.add_argument("--lang=en")  # Force English language
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36")  # Set a common user agent
    
    service = Service(executable_path=chrome_driver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)

    # Twitter often requires a larger viewport to display content properly
    driver.set_window_size(1920, 1080)

    url = f"https://twitter.com/search?q={search_term}&src=typed_query&f=live"  # Adding &f=live for recent tweets
    print(f"Accessing URL: {url}")
    driver.get(url)
    
    # Wait for page to load initially
    time.sleep(5)
    
    # Check if we're on a login page or access is restricted
    if "log in" in driver.title.lower() or any(x in driver.page_source.lower() for x in ["sign up", "log in to twitter"]):
        print("Warning: Twitter may be requiring login. Limited results expected.")
    
    tweets = []
    last_height = driver.execute_script("return document.body.scrollHeight")
    scroll_attempts = 0
    max_attempts = 25
    consecutive_empty_scrolls = 0
    max_empty_scrolls = 3
    
    print("Starting to scroll and collect tweets...")
    
    while scroll_attempts < max_attempts:
        # Scroll down
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)  # Adjusted wait time
        
        # Get new tweets before checking height
        try:
            # Try multiple selectors to find tweets
            all_articles = driver.find_elements("xpath", "//article")
            
            if all_articles:
                print(f"Found {len(all_articles)} articles in scroll {scroll_attempts+1}")
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
                    except:
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
                    except:
                        continue
                    
                    # Get username
                    try:
                        username_elements = article.find_elements("xpath", ".//div[@data-testid='User-Name']")
                        if username_elements:
                            tweet_data["username"] = username_elements[0].text.split('\n')[0]
                        else:
                            tweet_data["username"] = "unknown"
                    except:
                        tweet_data["username"] = "unknown"
                    
                    # Get hashtags
                    try:
                        hashtag_links = article.find_elements("xpath", ".//a[contains(@href, '/hashtag/')]")
                        tweet_data["hashtags"] = [link.text for link in hashtag_links if link.text.startswith('#')]
                    except:
                        tweet_data["hashtags"] = []
                    
                    if "text" in tweet_data and tweet_data["text"].strip():
                        tweets.append(tweet_data)
                
                # Check if we got new tweets
                if len(tweets) == tweets_before:
                    consecutive_empty_scrolls += 1
                else:
                    consecutive_empty_scrolls = 0
            else:
                consecutive_empty_scrolls += 1
                print("No articles found in this scroll")
        except Exception as e:
            print(f"Error while parsing tweets: {str(e)}")
        
        # Check if scrolled to bottom or no new content
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height or consecutive_empty_scrolls >= max_empty_scrolls:
            print(f"Reached bottom or no new tweets after {consecutive_empty_scrolls} attempts")
            break
        
        last_height = new_height
        scroll_attempts += 1
        print(f"Completed scroll {scroll_attempts}/{max_attempts}, found {len(tweets)} tweets so far")

    print(f"Scraping complete. Found {len(tweets)} tweets.")
    
    # Save HTML for debugging
    html = driver.page_source
    with open("debug.html", "w", encoding="utf-8") as f:
        f.write(html)

    driver.quit()
    
    # Final check to remove any remaining duplicates
    unique_tweets = []
    seen_texts = set()
    
    for tweet in tweets:
        text = tweet.get("text", "").strip()
        if text and text not in seen_texts:
            seen_texts.add(text)
            unique_tweets.append(tweet)
    

    unique_tweets = remove_duplicates(unique_tweets)
    print(f"After removing duplicates: {len(unique_tweets)} tweets")
    return unique_tweets

def calculate_relevancy_score(tweets: list, search_term: str) -> tuple:
    if not tweets:
        print("Warning: No tweets to process for relevancy scoring.")
        return [], 0
    
    try:
        nltk.download("stopwords", quiet=True)
        stop_words = set(stopwords.words("english"))

        texts = [t.get("text", "") for t in tweets if t.get("text")]
        if not texts:
            print("Warning: No valid tweet texts for processing.")
            return tweets, 0
            
        all_docs = [search_term] + texts
        
        # Handle very short or identical documents
        if len(set(all_docs)) <= 1:
            print("Warning: Not enough unique content for meaningful analysis.")
            for tweet in tweets:
                tweet["relevancy_score"] = 50  # Assign neutral score
            return tweets, 50

        vectorizer = TfidfVectorizer(stop_words=stop_words)
        tfidf = vectorizer.fit_transform(all_docs)

        sim_scores = cosine_similarity(tfidf[0:1], tfidf[1:]).flatten()
        for i, score in enumerate(sim_scores):
            tweets[i]["relevancy_score"] = int(score * 100)
        trend_score = int(sim_scores.mean() * 100) if len(sim_scores) > 0 else 0
        
        return tweets, trend_score
    except Exception as e:
        print(f"Error in relevancy calculation: {str(e)}")
        # Assign default scores in case of failure
        for tweet in tweets:
            tweet["relevancy_score"] = 0
        return tweets, 0

def remove_duplicates(tweets: list) -> list:
    """
    Remove duplicate tweets based on the hash of the tweet text.
    """
    seen = set()
    unique = []
    for t in tweets:
        h = hash(t["text"])
        if h not in seen:
            seen.add(h)
            unique.append(t)
    return unique


def save_to_yaml(data: dict, filename: str) -> None:
    """
    Dump the given data dict to a YAML file.
    """
    with open(filename, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


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
    for title, cond in segments.items():
        group = [t for t in tweets if cond(t)]
        if not group:
            continue
        print(f"\n=== {title} Relevancy ===")
        for t in group:
            print(f"[{t['relevancy_score']:>3}] {t['username']}: {t['text']}")


def analyze_twitter_trend(search_term: str,
                          save_raw: bool = True,
                          save_scored: bool = True) -> dict:
    """
    Main pipeline: scrape → dedupe → score → save → display.
    Returns a dict {'trend_relevancy': int, 'tweets': list}.
    """
    # 1) Scrape
    raw_tweets = scrape_twitter_trends(search_term)
    print(f"Scraped tweets: {len(raw_tweets)}")  # Debugging line
    if not raw_tweets:
        print("No tweets found for the given search term.")
        return

    # 2) Deduplicate
    unique_tweets = remove_duplicates(raw_tweets)
    print(f"Unique tweets after deduplication: {len(unique_tweets)}")
    if not unique_tweets:
        print("No unique tweets found after deduplication.")
        return

    # 3) Optional: Save raw
    if save_raw:
        raw_fn = f"{search_term.replace(' ', '_')}_raw.yaml"
        save_to_yaml({"raw_tweets": unique_tweets}, raw_fn)
        print(f"▶︎ Raw tweets saved to {raw_fn}")

    # 4) Score
    scored_tweets, trend_score = calculate_relevancy_score(unique_tweets, search_term)

    # 5) Sort descending
    sorted_tweets = sorted(scored_tweets,
                           key=lambda x: x["relevancy_score"],
                           reverse=True)

    # 6) Optional: Save scored
    if save_scored:
        out = {"trend_relevancy": trend_score, "tweets": sorted_tweets}
        out_fn = f"{search_term.replace(' ', '_')}_results.yaml"
        save_to_yaml(out, out_fn)
        print(f"▶︎ Scored results saved to {out_fn}")

    # 7) Display on console
    display_by_segments(sorted_tweets)

    return {"trend_relevancy": trend_score, "tweets": sorted_tweets}


if __name__ == "__main__":
    try:
        print("Twitter Trend Analysis Tool")
        print("==========================")
        term = input("Enter search term: ").strip()
        
        if not term:
            print("Error: Search term cannot be empty.")
            exit(1)
            
        print(f"\nAnalyzing Twitter for: '{term}'")
        print("This may take a few minutes. Please wait...\n")
        
        start_time = time.time()
        results = analyze_twitter_trend(term)
        elapsed_time = time.time() - start_time
        
        if results and results.get("tweets"):
            print(f"\nAnalysis completed in {elapsed_time:.1f} seconds.")
            print(f"Overall trend relevancy score: {results['trend_relevancy']}/100")
            print(f"Found {len(results['tweets'])} relevant tweets.")
        else:
            print("\nNo relevant results found. Try a different search term or check your internet connection.")
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {str(e)}")