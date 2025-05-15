from flask import Flask, render_template, request, Response, jsonify
import os
import yaml
import json
import time
from datetime import datetime
import re
from collections import Counter
import v8 as twitter_analyzer  # Import your existing Twitter analyzer script

app = Flask(__name__)

# Directory paths
RAW_TWEETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tweets", "raw")
RESULTS_TWEETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tweets", "results")

# Ensure directories exist
os.makedirs(RAW_TWEETS_DIR, exist_ok=True)
os.makedirs(RESULTS_TWEETS_DIR, exist_ok=True)

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
    """Get details for a specific term"""
    term = request.args.get('term', '')
    if not term:
        return jsonify({"error": "No term provided"}), 400
    
    filename = os.path.join(RESULTS_TWEETS_DIR, f"{term.replace(' ', '_')}_results.yaml")
    
    if not os.path.exists(filename):
        return jsonify({"error": "Term not found"}), 404
    
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            data = yaml.safe_load(file)
        
        # Calculate sentiment from tweets
        sentiment = calculate_sentiment(data.get('tweets', []))
        
        # Return the top 10 most relevant tweets
        top_tweets = sorted(
            data.get('tweets', []),
            key=lambda t: t.get('relevancy_score', 0),
            reverse=True
        )[:10]
        
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
    
    # Calculate overall sentiment
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
    Simple sentiment analysis based on relevancy scores
    In a real implementation, you would use a proper sentiment analysis model
    """
    if not tweets:
        return {"positive": 33, "neutral": 34, "negative": 33}
    
    positive = 0
    neutral = 0
    negative = 0
    
    for tweet in tweets:
        score = tweet.get('relevancy_score', 50)
        
        if score >= 75:
            positive += 1
        elif score >= 40:
            neutral += 1
        else:
            negative += 1
    
    total = positive + neutral + negative
    if total == 0:
        return {"positive": 33, "neutral": 34, "negative": 33}
    
    return {
        "positive": round((positive / total) * 100),
        "neutral": round((neutral / total) * 100),
        "negative": round((negative / total) * 100)
    }

if __name__ == '__main__':
    app.run(debug=True)
