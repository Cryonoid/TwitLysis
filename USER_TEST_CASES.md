# Twitter Trend Analysis Bot – Sample User Test Cases Guide

This guide walks you through installation, running the script, and verifying outputs.

## 1. Install Dependencies 

```bash
pip install -r requirements.txt
```

## 2. Run the Script

```bash
python twitter_trend_analysis.py
```

## 3. Verify Outputs

The script will output the following:

- Raw tweets saved to `{search_term}_raw.yaml`
- Scored results saved to `{search_term}_results.yaml`
- Console display of tweets grouped by relevancy

## 4. Test Cases

### 4.1. Basic Search   

```bash
python twitter_trend_analysis.py
```

### 4.2. Save Raw Tweets    

```bash
python twitter_trend_analysis.py --save_raw
```

### 4.3. Save Scored Results            

```bash
python twitter_trend_analysis.py --save_scored
```

### 4.4. Custom Search Term (e.g., "AI")

```bash
python twitter_trend_analysis.py --search_term "AI"
```

### 4.5. Custom Search Term (e.g., "AI") with Save Raw and Save Scored  

```bash
python twitter_trend_analysis.py --search_term "AI" --save_raw --save_scored
```
