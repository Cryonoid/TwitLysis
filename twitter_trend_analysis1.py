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
import yaml
from bs4 import BeautifulSoup
import nltk
from nltk.corpus import stopwords
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# def scrape_twitter_trends(search_term: str) -> list:
#     chrome_driver_path = r"C:\Users\incre\Downloads\chromedriver-win64\chromedriver-win64\chromedriver.exe"

#     chrome_options = Options()
#     chrome_options.add_argument("--headless")
#     chrome_options.add_argument("--disable-gpu")
#     chrome_options.add_argument("--no-sandbox")
#     chrome_options.add_argument("--disable-dev-shm-usage")

#     service = Service(executable_path=chrome_driver_path)
#     driver = webdriver.Chrome(service=service, options=chrome_options)

#     driver.get(f"https://twitter.com/search?q={search_term}&src=typed_query&f=live")
#     time.sleep(5)  # Let the page load

#     for _ in range(5):  # Scroll to load more tweets
#         driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
#         time.sleep(2)

#     html = driver.page_source
#     driver.quit()

#     soup = BeautifulSoup(html, "html.parser")
#     tweets = []
#     for article in soup.find_all("article"):
#         try:
#             text_el = article.find("div", {"data-testid": "tweetText"})
#             if not text_el:
#                 continue
#             text = text_el.get_text().strip()

#             username_el = article.find("div", {"dir": "ltr"})
#             username = username_el.get_text().strip() if username_el else "unknown"

#             hashtags = [
#                 tag.get_text() for tag in article.find_all(
#                     "a", {"href": lambda x: x and "hashtag" in x}
#                 )
#             ]
#             tweets.append({"text": text, "username": username, "hashtags": hashtags})
#         except Exception:
#             continue

#     return tweets


# def scrape_twitter_trends(search_term: str) -> list:
    # chrome_driver_path = r"C:\Users\incre\Downloads\chromedriver-win64\chromedriver-win64\chromedriver.exe"

    # chrome_options = Options()
    # chrome_options.add_argument("--headless")  # Run in headless mode
    # chrome_options.add_argument("--disable-gpu")
    # chrome_options.add_argument("--no-sandbox")
    # service = Service(executable_path=chrome_driver_path)
    # driver = webdriver.Chrome(service=service, options=chrome_options)

    # driver.get(f"https://twitter.com/search?q={search_term}&src=typed_query&f=live")
    # time.sleep(10)  # Let the page load

#     for _ in range(5):  # Scroll to load more tweets
#         driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
#         time.sleep(4)

#     html = driver.page_source
#     driver.quit()

#     soup = BeautifulSoup(html, "html.parser")
#     tweets = []
#     articles = soup.find_all("article")
#     for article in soup.find_all("article"):
#         try:
#             text_el = article.find("div", {"data-testid": "tweetText"})
#             if not text_el:
#                 continue
#             text = text_el.get_text().strip()
#             print(f"Found tweet: {text}")  # Debugging line

#             username_el = article.find("div", {"dir": "ltr"})
#             username = username_el.get_text().strip() if username_el else "unknown"

#             hashtags = [
#                 tag.get_text() for tag in article.find_all(
#                     "a", {"href": lambda x: x and "hashtag" in x}
#                 )
#             ]
#             tweets.append({"text": text, "username": username, "hashtags": hashtags})
#         except Exception:
#             continue

#     return tweets


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


def calculate_relevancy_score(tweets: list, search_term: str) -> tuple:
    """
    Vectorize tweets + search_term using TF-IDF and compute cosine similarity.
    Returns updated tweets with 'relevancy_score' and the average trend relevancy.
    """
    nltk.download("stopwords", quiet=True)
    stop_words = set(stopwords.words("english"))

    texts = [t["text"] for t in tweets]
    all_docs = [search_term] + texts
    vectorizer = TfidfVectorizer(stop_words=stop_words)
    tfidf = vectorizer.fit_transform(all_docs)

    sim_scores = cosine_similarity(tfidf[0:1], tfidf[1:]).flatten()
    for i, score in enumerate(sim_scores):
        tweets[i]["relevancy_score"] = int(score * 100)
    trend_score = int(sim_scores.mean() * 100)
    return tweets, trend_score


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
    # 2) Deduplicate
    unique_tweets = remove_duplicates(raw_tweets)

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
    term = input("Enter search term: ").strip()
    analyze_twitter_trend(term) 
