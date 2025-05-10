# Twitter Trend Analysis Bot

## Project Overview
A Python-based tool that analyzes Twitter trends without API access, providing relevancy scores for hashtags and posts related to searched topics.

## Objectives
- Create a Twitter trend analysis system without using the official Twitter API
- Implement a relevancy scoring algorithm (0-100) for trending topics
- Filter out irrelevant content in search results
- Prevent duplicate results in the output

## Technical Approach

Since Twitter API access is not available, we'll use web scraping with DOM manipulation:

```python
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import pandas as pd
import nltk
from nltk.corpus import stopwords
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import time
```

## Implementation Details

### 1. Data Collection
```python
def scrape_twitter_trends(search_term):
    # Setup headless browser
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    driver = webdriver.Chrome(options=chrome_options)
    
    # Navigate to Twitter search
    driver.get(f"https://twitter.com/search?q={search_term}&src=typed_query&f=live")
    time.sleep(5)  # Allow page to load
    
    # Scroll to load more content
    for _ in range(5):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
    
    # Get page content
    html = driver.page_source
    driver.quit()
    
    # Parse HTML
    soup = BeautifulSoup(html, 'html.parser')
    tweets = []
    
    # Extract tweets (specific selectors would need updating based on current Twitter DOM)
    tweet_elements = soup.find_all('article')
    for tweet in tweet_elements:
        try:
            text_element = tweet.find('div', {'lang': True})
            if text_element:
                text = text_element.get_text()
                username = tweet.find('span', {'class': 'username'}).get_text()
                hashtags = [tag.get_text() for tag in tweet.find_all('a', {'href': lambda x: x and 'hashtag' in x})]
                tweets.append({'text': text, 'username': username, 'hashtags': hashtags})
        except:
            continue
            
    return tweets
```

### 2. Relevancy Scoring Algorithm
```python
def calculate_relevancy_score(tweets, search_term):
    # Prepare data
    nltk.download('stopwords')
    stop_words = set(stopwords.words('english'))
    
    # Extract text content
    texts = [tweet['text'] for tweet in tweets]
    
    # Create search term document
    search_doc = search_term
    
    # All documents (search term + tweets)
    all_docs = [search_doc] + texts
    
    # TF-IDF Vectorization
    vectorizer = TfidfVectorizer(stop_words=stop_words)
    tfidf_matrix = vectorizer.fit_transform(all_docs)
    
    # Calculate cosine similarity between search term and each tweet
    search_vector = tfidf_matrix[0:1]
    tweet_vectors = tfidf_matrix[1:]
    similarity_scores = cosine_similarity(search_vector, tweet_vectors).flatten()
    
    # Assign scores to tweets
    for i, score in enumerate(similarity_scores):
        tweets[i]['relevancy_score'] = int(score * 100)
    
    # Calculate overall trend relevancy
    trend_relevancy = int(similarity_scores.mean() * 100)
    
    return tweets, trend_relevancy
```

### 3. Result Deduplication
```python
def remove_duplicates(tweets):
    seen = set()
    unique_tweets = []
    
    for tweet in tweets:
        # Create a hash of the tweet text to check for duplicates
        text_hash = hash(tweet['text'])
        if text_hash not in seen:
            seen.add(text_hash)
            unique_tweets.append(tweet)
            
    return unique_tweets
```

### 4. Main Function
```python
def analyze_twitter_trend(search_term):
    # Collect data
    tweets = scrape_twitter_trends(search_term)
    
    # Remove duplicates
    unique_tweets = remove_duplicates(tweets)
    
    # Calculate relevancy scores
    scored_tweets, trend_relevancy = calculate_relevancy_score(unique_tweets, search_term)
    
    # Sort by relevancy
    sorted_tweets = sorted(scored_tweets, key=lambda x: x['relevancy_score'], reverse=True)
    
    return {
        'trend_relevancy': trend_relevancy,
        'tweets': sorted_tweets
    }
```

## Environment Requirements

```
# requirements.txt
selenium==4.9.1
beautifulsoup4==4.12.2
pandas==2.0.1
nltk==3.8.1
scikit-learn==1.2.2
```

## Challenges and Limitations

- **DOM Changes**: Twitter frequently updates its HTML structure, requiring regular maintenance
- **Rate Limiting**: Excessive scraping might trigger IP blocks
- **Legal Considerations**: Web scraping may violate Twitter's Terms of Service
- **Quality**: Without API access, data quality and consistency might be lower

## Future Improvements

- Implement proxy rotation to avoid rate limiting
- Add sentiment analysis to enhance trend understanding
- Create visualization dashboard for trend analysis results
- Implement advanced NLP techniques for improved relevancy scoring