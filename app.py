from flask import Flask, render_template, request, Response, jsonify
import os
import yaml
import json
import time
import math
from datetime import datetime
import re
from collections import Counter
import v8 as twitter_analyzer  # Import your existing Twitter analyzer script

# VADER sentiment analysis (part of NLTK, no extra dependency)
import nltk
from nltk.sentiment.vader import SentimentIntensityAnalyzer

app = Flask(__name__)

# Directory paths
RAW_TWEETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tweets", "raw")
RESULTS_TWEETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tweets", "results")

# Ensure directories exist
os.makedirs(RAW_TWEETS_DIR, exist_ok=True)
os.makedirs(RESULTS_TWEETS_DIR, exist_ok=True)

# Lazy-loaded VADER instance (downloads lexicon on first use)
_vader = None

def _get_vader():
    """Lazy-load VADER sentiment analyzer. Downloads lexicon on first run (~500KB)."""
    global _vader
    if _vader is None:
        try:
            nltk.data.find('sentiment/vader_lexicon.zip')
        except LookupError:
            print("[SETUP] Downloading VADER sentiment lexicon (one-time, ~500KB)...")
            nltk.download('vader_lexicon', quiet=True)
        _vader = SentimentIntensityAnalyzer()
    return _vader

def _parse_engagement(tweet):
    """Parse engagement_raw aria-labels into numeric values."""
    result = {"replies": 0, "retweets": 0, "likes": 0, "views": 0}
    for label in tweet.get("engagement_raw", []):
        label_lower = label.lower()
        # Extract number from strings like "12 likes", "1,542 views"
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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/search')
def search():
    query = request.args.get('query', '')
    if not query:
        return jsonify({"error": "No query provided"}), 400
    
    def generate():
        try:
            # Initialize the generator from twitter_analyzer
            message_generator = twitter_analyzer.run_twitter_analysis_script(query)
            
            # Track progress through stages
            current_step = 0
            total_steps = 5
            
            # Process each message from the generator
            for message in message_generator:
                # Track progress based on step indicators
                if "[STEP " in message:
                    try:
                        step_num = int(message.split("[STEP ")[1].split("/")[0])
                        current_step = step_num
                    except (ValueError, IndexError):
                        pass
                
                # Calculate progress percentage
                progress = min(int((current_step / total_steps) * 100), 95)
                
                # Format message as SSE data
                data = {
                    "message": message,
                    "progress": progress
                }
                
                yield f"data: {json.dumps(data)}\n\n"
                time.sleep(0.05)  # Small delay for client processing
            
            # Signal completion with 100%
            yield f"data: {json.dumps({'message': '[COMPLETE] Analysis finished and results ready.', 'progress': 100})}\n\n"
            
        except Exception as e:
            # Send error message to client
            error_data = {
                "error": True, 
                "message": f"[ERROR] An error occurred: {str(e)}"
            }
            yield f"data: {json.dumps(error_data)}\n\n"
    
    return Response(generate(), content_type='text/event-stream')

@app.route('/api/available-terms')
def get_available_terms():
    """Return list of terms for which we have analysis results"""
    terms = []
    
    if os.path.exists(RESULTS_TWEETS_DIR):
        for filename in os.listdir(RESULTS_TWEETS_DIR):
            if filename.endswith('.yaml'):
                term = filename.replace('_results.yaml', '').replace('_', ' ')
                terms.append(term)
    
    return jsonify(terms)

@app.route('/api/term-details')
def get_term_details():
    """Get details for a specific term including VADER sentiment and engagement data"""
    term = request.args.get('term', '')
    if not term:
        return jsonify({"error": "No term provided"}), 400
    
    filename = os.path.join(RESULTS_TWEETS_DIR, f"{term.replace(' ', '_')}_results.yaml")
    
    if not os.path.exists(filename):
        return jsonify({"error": "Term not found"}), 404
    
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            data = yaml.safe_load(file)
        
        # Calculate VADER sentiment from tweet text
        sentiment = calculate_sentiment(data.get('tweets', []))
        
        # Return the top 10 most relevant tweets
        top_tweets = sorted(
            data.get('tweets', []),
            key=lambda t: t.get('relevancy_score', 0),
            reverse=True
        )[:10]

        # Ensure tweet_url is present for linking back to X
        for tweet in top_tweets:
            if 'tweet_url' not in tweet and tweet.get('id', '').isdigit():
                user = tweet.get('username', '').lstrip('@')
                if user:
                    tweet['tweet_url'] = f"https://x.com/{user}/status/{tweet['id']}"
            # Parse engagement for display
            tweet['engagement'] = _parse_engagement(tweet)
        
        return jsonify({
            "term": term,
            "trend_score": data.get('trend_relevancy', 0),
            "tweet_count": len(data.get('tweets', [])),
            "sentiment": sentiment,
            "tweets": top_tweets
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/trends')
def get_trends():
    """Get overall trend analysis"""
    top_trends = []
    all_tweets = []
    
    if os.path.exists(RESULTS_TWEETS_DIR):
        term_counts = {}
        
        for filename in os.listdir(RESULTS_TWEETS_DIR):
            if filename.endswith('_results.yaml'):
                try:
                    with open(os.path.join(RESULTS_TWEETS_DIR, filename), 'r', encoding='utf-8') as file:
                        data = yaml.safe_load(file)
                        term = data.get('search_term', filename.replace('_results.yaml', '').replace('_', ' '))
                        term_counts[term] = len(data.get('tweets', []))
                        all_tweets.extend(data.get('tweets', []))
                except:
                    continue
                    
        # Get top trends by tweet count
        top_trends = [{"term": term, "count": count} for term, count in 
                     sorted(term_counts.items(), key=lambda x: x[1], reverse=True)[:10]]
    
    # Calculate overall VADER sentiment
    sentiment_overview = calculate_sentiment(all_tweets)
    
    return jsonify({
        "top_trends": top_trends,
        "sentiment_overview": sentiment_overview
    })

@app.route('/api/hashtags')
def get_hashtags():
    """Get popular hashtags from all tweets"""
    hashtags_counter = Counter()
    
    if os.path.exists(RESULTS_TWEETS_DIR):
        for filename in os.listdir(RESULTS_TWEETS_DIR):
            if filename.endswith('_results.yaml'):
                try:
                    with open(os.path.join(RESULTS_TWEETS_DIR, filename), 'r', encoding='utf-8') as file:
                        data = yaml.safe_load(file)
                        tweets = data.get('tweets', [])
                        
                        for tweet in tweets:
                            # Get hashtags from the hashtags field if available
                            tweet_hashtags = tweet.get('hashtags', [])
                            
                            # Also extract hashtags from the text
                            if 'text' in tweet:
                                text_hashtags = re.findall(r'#\w+', tweet['text'])
                                tweet_hashtags.extend(text_hashtags)
                            
                            # Count unique hashtags in this tweet
                            if tweet_hashtags:
                                hashtags_counter.update(tweet_hashtags)
                except:
                    continue
    
    # Convert to format expected by frontend
    hashtags = [{"text": tag, "count": count} for tag, count in hashtags_counter.most_common(50)]
    
    return jsonify({"hashtags": hashtags})

@app.route('/api/previous-results')
def get_previous_results():
    """Get list of previous analysis results"""
    results = []
    
    if os.path.exists(RESULTS_TWEETS_DIR):
        for filename in os.listdir(RESULTS_TWEETS_DIR):
            if filename.endswith('_results.yaml'):
                try:
                    file_path = os.path.join(RESULTS_TWEETS_DIR, filename)
                    file_stat = os.stat(file_path)
                    file_date = datetime.fromtimestamp(file_stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                    
                    with open(file_path, 'r', encoding='utf-8') as file:
                        data = yaml.safe_load(file)
                        
                        results.append({
                            "term": data.get('search_term', filename.replace('_results.yaml', '').replace('_', ' ')),
                            "score": data.get('trend_relevancy', 0),
                            "tweet_count": len(data.get('tweets', [])),
                            "date": file_date
                        })
                except:
                    continue
    
    # Sort by date, newest first
    results.sort(key=lambda x: x["date"], reverse=True)
    
    return jsonify(results)

def calculate_sentiment(tweets):
    """
    Two-layer sentiment analysis:
      Layer 1: VADER NLP — actual language sentiment on each tweet's text
      Layer 2: Engagement weighting — high-engagement tweets carry more signal weight
    
    Returns dict with percentage breakdown, weighted compound score, and signal strength.
    """
    if not tweets:
        return {"positive": 33, "neutral": 34, "negative": 33,
                "avg_compound": 0, "signal_strength": "none"}
    
    sia = _get_vader()
    weighted_compounds = []
    positive = neutral = negative = 0
    
    for tweet in tweets:
        text = tweet.get('text', '')
        if not text.strip():
            neutral += 1
            continue
        
        scores = sia.polarity_scores(text)
        compound = scores['compound']
        
        # Engagement weight: tweets with more interaction carry more signal
        eng = _parse_engagement(tweet)
        impact = eng["likes"] + eng["retweets"] * 2 + eng["replies"]
        weight = math.log1p(impact) if impact > 0 else 1.0
        
        weighted_compounds.append((compound, weight))
        
        if compound >= 0.05:
            positive += 1
        elif compound <= -0.05:
            negative += 1
        else:
            neutral += 1
    
    total = positive + neutral + negative
    if total == 0:
        return {"positive": 33, "neutral": 34, "negative": 33,
                "avg_compound": 0, "signal_strength": "none"}
    
    # Weighted average compound score
    total_weight = sum(w for _, w in weighted_compounds)
    avg_compound = sum(c * w for c, w in weighted_compounds) / total_weight if total_weight > 0 else 0
    
    # Signal strength classification
    if abs(avg_compound) > 0.5:
        signal = "strong"
    elif abs(avg_compound) > 0.2:
        signal = "moderate"
    else:
        signal = "weak"
    
    return {
        "positive": round((positive / total) * 100),
        "neutral": round((neutral / total) * 100),
        "negative": round((negative / total) * 100),
        "avg_compound": round(avg_compound, 3),
        "signal_strength": signal
    }

if __name__ == '__main__':
    app.run(debug=True)
