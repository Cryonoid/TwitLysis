from flask import Flask, render_template, request, Response, jsonify
import os
import yaml
import json
import time
import math
import csv
import io
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
    use_aliases = request.args.get('alias', 'false').lower() == 'true'
    if not query:
        return jsonify({"error": "No query provided"}), 400
    
    def generate():
        try:
            # Initialize the generator from twitter_analyzer
            message_generator = twitter_analyzer.run_twitter_analysis_script(query, use_aliases=use_aliases)
            
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
        all_raw_tweets = data.get('tweets', [])
        sentiment = calculate_sentiment(all_raw_tweets)
        
        # Return top 25 most relevant tweets (was 10)
        top_tweets = sorted(
            all_raw_tweets,
            key=lambda t: t.get('relevancy_score', 0),
            reverse=True
        )[:25]

        # Ensure tweet_url is present for linking back to X
        for tweet in top_tweets:
            if 'tweet_url' not in tweet and tweet.get('id', '').isdigit():
                user = tweet.get('username', '').lstrip('@')
                if user:
                    tweet['tweet_url'] = f"https://x.com/{user}/status/{tweet['id']}"
            # Parse engagement for display
            tweet['engagement'] = _parse_engagement(tweet)
        
        # Prepare ALL tweets with minimal fields for cluster browsing
        # (cluster tweet_indices reference positions in the full list)
        all_tweets_slim = []
        for i, tweet in enumerate(all_raw_tweets):
            eng = _parse_engagement(tweet)
            if 'tweet_url' not in tweet and tweet.get('id', '').isdigit():
                user = tweet.get('username', '').lstrip('@')
                if user:
                    tweet['tweet_url'] = f"https://x.com/{user}/status/{tweet['id']}"
            all_tweets_slim.append({
                "index": i,
                "text": tweet.get('text', '')[:200],
                "username": tweet.get('username', ''),
                "relevancy_score": tweet.get('relevancy_score', 0),
                "language": tweet.get('language', 'en'),
                "spam_flag": tweet.get('spam_flag', False),
                "influence_score": tweet.get('influence_score', 0),
                "engagement": eng,
                "tweet_url": tweet.get('tweet_url', '')
            })
        
        # Extract enhanced v3 data (clusters, velocity, language distribution)
        clusters = data.get('clusters', {})
        velocity = data.get('velocity', {})
        lang_dist = data.get('language_distribution', {})
        spam_count = data.get('spam_flagged_count', 0)
        high_influence = data.get('high_influence_count', 0)
        search_context = data.get('search_context', 'general')
        
        return jsonify({
            "term": term,
            "trend_score": data.get('trend_relevancy', 0),
            "tweet_count": len(all_raw_tweets),
            "sentiment": sentiment,
            "tweets": top_tweets,
            "all_tweets": all_tweets_slim,
            "clusters": clusters,
            "velocity": velocity,
            "language_distribution": lang_dist,
            "spam_flagged_count": spam_count,
            "high_influence_count": high_influence,
            "search_context": search_context
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/trends')
def get_trends():
    """Get overall trend analysis with per-term sentiment and top hashtags."""
    top_trends = []
    all_tweets = []
    term_data = {}  # term -> {tweets, hashtags_counter}
    
    if os.path.exists(RESULTS_TWEETS_DIR):
        for filename in os.listdir(RESULTS_TWEETS_DIR):
            if filename.endswith('_results.yaml'):
                try:
                    with open(os.path.join(RESULTS_TWEETS_DIR, filename), 'r', encoding='utf-8') as file:
                        data = yaml.safe_load(file)
                        term = data.get('search_term', filename.replace('_results.yaml', '').replace('_', ' '))
                        tweets = data.get('tweets', [])
                        
                        # Collect hashtags for this term
                        ht_counter = Counter()
                        for tweet in tweets:
                            for h in tweet.get('hashtags', []):
                                ht_counter[h] += 1
                            if 'text' in tweet:
                                for h in re.findall(r'#\w+', tweet['text']):
                                    ht_counter[h] += 1
                        
                        term_data[term] = {
                            "tweets": tweets,
                            "hashtags": ht_counter,
                            "velocity": data.get('velocity', {})
                        }
                        all_tweets.extend(tweets)
                except:
                    continue
        
        # Build enriched trend objects sorted by tweet count
        sorted_terms = sorted(term_data.items(), key=lambda x: len(x[1]["tweets"]), reverse=True)[:10]
        for term, info in sorted_terms:
            sentiment = calculate_sentiment(info["tweets"])
            top_ht = [tag for tag, _ in info["hashtags"].most_common(3)]
            top_trends.append({
                "term": term,
                "count": len(info["tweets"]),
                "sentiment_signal": sentiment.get("signal_strength", "none"),
                "avg_compound": sentiment.get("avg_compound", 0),
                "top_hashtags": top_ht,
                "velocity": info.get("velocity", {})
            })
    
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
    """Get list of previous analysis results with sentiment preview and top tweet snippet."""
    results = []
    
    if os.path.exists(RESULTS_TWEETS_DIR):
        for filename in os.listdir(RESULTS_TWEETS_DIR):
            if filename.endswith('_results.yaml'):
                try:
                    file_path = os.path.join(RESULTS_TWEETS_DIR, filename)
                    file_stat = os.stat(file_path)
                    # Send ISO timestamp so frontend can compute relative time
                    file_date_iso = datetime.fromtimestamp(file_stat.st_mtime).isoformat()
                    
                    with open(file_path, 'r', encoding='utf-8') as file:
                        data = yaml.safe_load(file)
                    
                    tweets = data.get('tweets', [])
                    sentiment = calculate_sentiment(tweets)
                    
                    # Get preview from highest-relevancy tweet
                    top_tweet_preview = ""
                    if tweets:
                        best = max(tweets, key=lambda t: t.get('relevancy_score', 0))
                        text = best.get('text', '')
                        top_tweet_preview = text[:100] + ('…' if len(text) > 100 else '')
                    
                    results.append({
                        "term": data.get('search_term', filename.replace('_results.yaml', '').replace('_', ' ')),
                        "score": data.get('trend_relevancy', 0),
                        "tweet_count": len(tweets),
                        "date": file_date_iso,
                        "sentiment_signal": sentiment.get("signal_strength", "none"),
                        "avg_compound": sentiment.get("avg_compound", 0),
                        "top_tweet_preview": top_tweet_preview
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
    
    # TODO: FUTURE — Multilingual sentiment (VADER only supports English).
    # Non-English tweets currently receive neutral sentiment scores, which skews
    # overall distribution when many tweets are non-English (~40% in some datasets).
    # Future options: xml-roberta, language-specific VADER ports, or translation pipeline.
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
        
        # Skip VADER for non-English tweets (returns neutral)
        lang = tweet.get('language', 'en')
        if lang != 'en' and lang not in ('en', ''):
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


@app.route('/api/compare')
def compare_terms():
    """Compare 2-3 searched terms side-by-side."""
    terms_param = request.args.get('terms', '')
    if not terms_param:
        return jsonify({"error": "No terms provided"}), 400
    
    terms = [t.strip() for t in terms_param.split(',') if t.strip()][:3]
    if len(terms) < 2:
        return jsonify({"error": "Need at least 2 terms to compare"}), 400
    
    results = []
    all_hashtags = {}  # term -> set of hashtags
    
    for term in terms:
        filename = os.path.join(RESULTS_TWEETS_DIR, f"{term.replace(' ', '_')}_results.yaml")
        if not os.path.exists(filename):
            continue
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            tweets = data.get('tweets', [])
            sentiment = calculate_sentiment(tweets)
            
            # Total engagement
            total_likes = sum(_parse_engagement(t).get('likes', 0) for t in tweets)
            total_retweets = sum(_parse_engagement(t).get('retweets', 0) for t in tweets)
            total_replies = sum(_parse_engagement(t).get('replies', 0) for t in tweets)
            
            # Hashtags
            ht_set = set()
            for t in tweets:
                for h in t.get('hashtags', []):
                    ht_set.add(h)
            all_hashtags[term] = ht_set
            
            results.append({
                "term": term,
                "tweet_count": len(tweets),
                "trend_score": data.get('trend_relevancy', 0),
                "sentiment": sentiment,
                "total_engagement": {
                    "likes": total_likes,
                    "retweets": total_retweets,
                    "replies": total_replies
                },
                "top_hashtags": list(ht_set)[:10],
                "velocity": data.get('velocity', {})
            })
        except Exception:
            continue
    
    # Calculate shared and unique hashtags
    if len(all_hashtags) >= 2:
        all_sets = list(all_hashtags.values())
        shared = set.intersection(*all_sets) if all_sets else set()
        unique = {term: list(ht - shared) for term, ht in all_hashtags.items()}
    else:
        shared = set()
        unique = {}
    
    return jsonify({
        "terms": results,
        "shared_hashtags": list(shared)[:10],
        "unique_hashtags": unique
    })


@app.route('/api/categories')
def get_categories():
    """Return search term categories with their terms for category chips."""
    categories = {}
    icons = getattr(twitter_analyzer, 'CATEGORY_ICONS', {})
    search_terms = getattr(twitter_analyzer, 'SEARCH_TERMS', {})
    
    for category, terms in search_terms.items():
        categories[category] = {
            "icon": icons.get(category.lower(), "🔍"),
            "terms": terms
        }
    
    return jsonify(categories)


@app.route('/api/export')
def export_data():
    """Export term analysis data in multiple formats."""
    term = request.args.get('term', '')
    fmt = request.args.get('format', 'json')
    
    if not term:
        return jsonify({"error": "No term provided"}), 400
    
    filename = os.path.join(RESULTS_TWEETS_DIR, f"{term.replace(' ', '_')}_results.yaml")
    if not os.path.exists(filename):
        return jsonify({"error": "Term not found"}), 404
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        tweets = data.get('tweets', [])
        sentiment = calculate_sentiment(tweets)
        
        if fmt == 'json':
            return jsonify(data)
        
        elif fmt == 'csv':
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['Username', 'Text', 'Relevancy Score', 'Language',
                           'Likes', 'Retweets', 'Replies', 'Spam Flag',
                           'Influence Score', 'Tweet URL'])
            for t in tweets:
                eng = _parse_engagement(t)
                writer.writerow([
                    t.get('username', ''),
                    t.get('text', ''),
                    t.get('relevancy_score', 0),
                    t.get('language', 'en'),
                    eng.get('likes', 0),
                    eng.get('retweets', 0),
                    eng.get('replies', 0),
                    t.get('spam_flag', False),
                    t.get('influence_score', 0),
                    t.get('tweet_url', '')
                ])
            response = Response(output.getvalue(), content_type='text/csv')
            response.headers['Content-Disposition'] = f'attachment; filename={term}_export.csv'
            return response
        
        elif fmt == 'md':
            velocity = data.get('velocity', {})
            clusters = data.get('clusters', {})
            trend_dir = velocity.get('trend_direction', 'N/A')
            tpm = velocity.get('velocity_tpm', 0)
            
            md = f"## TwitLysis Report: \"{term}\"\n"
            md += f"**Trend Score**: {data.get('trend_relevancy', 0)}/100 | "
            md += f"**Sentiment**: {sentiment.get('signal_strength', 'N/A').title()} ({sentiment.get('avg_compound', 0):+.3f})\n"
            md += f"**Tweets Analyzed**: {len(tweets)} | "
            md += f"**Velocity**: {trend_dir} ({tpm} tpm)\n\n"
            
            if clusters.get('summary'):
                md += f"**Themes**: {clusters['summary']}\n\n"
            
            md += "### Top Tweets\n"
            sorted_tweets = sorted(tweets, key=lambda t: t.get('relevancy_score', 0), reverse=True)
            for i, t in enumerate(sorted_tweets[:5]):
                text = t.get('text', '')[:120].replace('\n', ' ')
                md += f"{i+1}. [{t.get('relevancy_score', 0)}%] {t.get('username', '?')}: {text}...\n"
            
            md += f"\n*Generated by TwitLysis • {datetime.now().strftime('%b %d, %Y')}*"
            return jsonify({"markdown": md})
        
        elif fmt == 'html':
            # Return HTML data that the frontend will build into a self-contained file
            sorted_tweets = sorted(tweets, key=lambda t: t.get('relevancy_score', 0), reverse=True)
            return jsonify({
                "term": term,
                "trend_score": data.get('trend_relevancy', 0),
                "tweet_count": len(tweets),
                "sentiment": sentiment,
                "velocity": data.get('velocity', {}),
                "clusters": data.get('clusters', {}),
                "top_tweets": [{
                    "username": t.get('username', ''),
                    "text": t.get('text', ''),
                    "score": t.get('relevancy_score', 0),
                    "language": t.get('language', 'en'),
                    "url": t.get('tweet_url', '')
                } for t in sorted_tweets[:20]]
            })
        
        return jsonify({"error": f"Unknown format: {fmt}"}), 400
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)
