document.addEventListener('DOMContentLoaded', function() {
    // Elements
    const searchForm = document.getElementById('search-form');
    const searchInput = document.getElementById('search-input');
    const loadingIndicator = document.getElementById('loading-indicator');
    const progressMessages = document.getElementById('progress-messages');
    const searchResultsSlider = document.getElementById('search-results-slider');
    const noResultsMessage = document.getElementById('no-results-message');
    const prevPageBtn = document.getElementById('prev-page');
    const nextPageBtn = document.getElementById('next-page');
    const tweetDetailContainer = document.getElementById('tweet-detail-container');
    const tweetDetailContent = document.getElementById('tweet-detail-content');
    const closeDetailBtn = document.getElementById('close-detail');
    
    // Templates
    const searchResultTemplate = document.getElementById('search-result-template');
    const tweetTemplate = document.getElementById('tweet-template');
    
    // State management
    let currentPage = 0;
    let totalPages = 0;
    const ITEMS_PER_PAGE = 6;
    let searchHistory = loadSearchHistory();
    
    // Initialize UI
    initializeUI();
    
    // Event listeners
    searchForm.addEventListener('submit', handleSearch);
    prevPageBtn.addEventListener('click', goToPrevPage);
    nextPageBtn.addEventListener('click', goToNextPage);
    closeDetailBtn.addEventListener('click', closeTweetDetail);
    
    // Functions
    function initializeUI() {
        // Display saved search history
        displaySearchResults();
        
        // Hide loading indicator initially
        loadingIndicator.style.display = 'none';
    }
    
    function handleSearch(e) {
        e.preventDefault();
        const searchTerm = searchInput.value.trim();
        
        if (!searchTerm) {
            alert('Please enter a search term');
            return;
        }
        
        // Show loading indicator
        loadingIndicator.style.display = 'flex';
        progressMessages.style.display = 'block';
        progressMessages.innerHTML = '<div>Starting search for "' + searchTerm + '"...</div>';
        
        // Clear input field
        searchInput.value = '';
        
        // Simulate API call to your Python backend
        // In a real implementation, this would be an actual fetch call to your backend
        simulateTwitterAnalysis(searchTerm)
            .then(result => {
                // Add to search history
                const newSearch = {
                    id: Date.now(),
                    term: searchTerm,
                    date: new Date().toISOString(),
                    trendRelevancy: result.trend_relevancy,
                    tweets: result.tweets,
                };
                
                searchHistory.unshift(newSearch);
                saveSearchHistory();
                
                // Update UI
                displaySearchResults();
                
                // Hide loading indicator
                loadingIndicator.style.display = 'none';
                progressMessages.style.display = 'none';
            })
            .catch(error => {
                console.error('Error during search:', error);
                progressMessages.innerHTML += '<div class="error">Error: ' + error.message + '</div>';
                loadingIndicator.style.display = 'none';
                // Keep progress messages visible so user can see the error
            });
    }
    
    async function simulateTwitterAnalysis(searchTerm) {
        // This is a placeholder for the actual API call to your Python backend
        // In a real implementation, you would make a fetch request to your server
        
        // Simulate a set of progress messages
        const messages = [
            "Initializing Chrome WebDriver...",
            "Setting up browser environment...",
            "Accessing Twitter search page...",
            "Scrolling to collect tweets...",
            "Found first batch of tweets...",
            "Continuing to scroll for more content...",
            "Processing collected tweets...",
            "Calculating relevancy scores...",
            "Finalizing results..."
        ];
        
        // Display simulated progress messages
        for (const msg of messages) {
            await new Promise(resolve => setTimeout(resolve, 800 + Math.random() * 1200));
            progressMessages.innerHTML += `<div>[${new Date().toLocaleTimeString()}] ${msg}</div>`;
            progressMessages.scrollTop = progressMessages.scrollHeight;
        }
        
        // Simulate a delay for the whole process
        await new Promise(resolve => setTimeout(resolve, 1500));
        
        // Generate sample result
        // In a real implementation, this would come from your Python backend
        return {
            trend_relevancy: Math.floor(Math.random() * 40) + 60, // 60-100
            tweets: generateSampleTweets(searchTerm, Math.floor(Math.random() * 15) + 5) // 5-20 tweets
        };
    }
    
    function generateSampleTweets(searchTerm, count) {
        const tweets = [];
        const usernames = ['@user123', '@twitterUser', '@realPerson', '@newsSource', '@techExpert'];
        const sampleContent = [
            `Just read about ${searchTerm} and I'm really impressed with the latest developments!`,
            `Anyone else following the ${searchTerm} trends? What are your thoughts?`,
            `Breaking: New information about ${searchTerm} has just been released! #trending`,
            `I can't believe what's happening with ${searchTerm} right now. This changes everything.`,
            `My opinion on ${searchTerm} might be unpopular, but I think we need to consider all angles.`
        ];
        
        for (let i = 0; i < count; i++) {
            const relevancyScore = Math.floor(Math.random() * 100);
            const tweetId = Date.now().toString() + i;
            
            tweets.push({
                id: tweetId,
                username: usernames[Math.floor(Math.random() * usernames.length)],
                text: sampleContent[Math.floor(Math.random() * sampleContent.length)],
                relevancy_score: relevancyScore,
                timestamp: new Date(Date.now() - Math.random() * 86400000).toISOString(), // Within last 24h
                tweet_url: `https://twitter.com/i/web/status/${tweetId}`,
                hashtags: i % 2 === 0 ? [`#${searchTerm.replace(/\s+/g, '')}`, '#Trending'] : []
            });
        }
        
        // Sort by relevancy
        return tweets.sort((a, b) => b.relevancy_score - a.relevancy_score);
    }
    
    function displaySearchResults() {
        if (searchHistory.length === 0) {
            noResultsMessage.style.display = 'block';
            prevPageBtn.disabled = true;
            nextPageBtn.disabled = true;
            return;
        }
        
        noResultsMessage.style.display = 'none';
        
        // Calculate pagination
        totalPages = Math.ceil(searchHistory.length / ITEMS_PER_PAGE);
        currentPage = Math.min(currentPage, totalPages - 1);
        
        // Update pagination buttons
        prevPageBtn.disabled = currentPage === 0;
        nextPageBtn.disabled = currentPage >= totalPages - 1;
        
        // Clear existing content
        while (searchResultsSlider.firstChild) {
            if (searchResultsSlider.firstChild === noResultsMessage) {
                break;
            }
            searchResultsSlider.removeChild(searchResultsSlider.firstChild);
        }
        
        // Get current page items
        const startIndex = currentPage * ITEMS_PER_PAGE;
        const endIndex = Math.min(startIndex + ITEMS_PER_PAGE, searchHistory.length);
        const currentItems = searchHistory.slice(startIndex, endIndex);
        
        // Create and append search result cards
        currentItems.forEach(search => {
            const searchResult = createSearchResultCard(search);
            searchResultsSlider.appendChild(searchResult);
        });
        
        // Position the slider for the current page
        updateSliderPosition();
    }
    
    function createSearchResultCard(search) {
        const template = searchResultTemplate.content.cloneNode(true);
        
        // Set search term and score
        template.querySelector('.search-term').textContent = search.term;
        const scoreElement = template.querySelector('.relevancy-score');
        scoreElement.textContent = `${search.trendRelevancy}%`;
        
        // Apply color based on relevancy
        if (search.trendRelevancy >= 75) {
            scoreElement.style.backgroundColor = 'var(--high-relevance)';
        } else if (search.trendRelevancy >= 50) {
            scoreElement.style.backgroundColor = 'var(--medium-relevance)';
        } else {
            scoreElement.style.backgroundColor = 'var(--low-relevance)';
        }
        
        // Set date and tweet count
        const searchDate = new Date(search.date);
        template.querySelector('.search-date').textContent = searchDate.toLocaleDateString();
        template.querySelector('.tweet-count').textContent = `${search.tweets.length} tweets`;
        
        // Add up to 3 top tweets
        const tweetList = template.querySelector('.tweet-list');
        const topTweets = search.tweets.slice(0, 3); // Get top 3 tweets
        
        topTweets.forEach(tweet => {
            const tweetElement = createTweetElement(tweet);
            tweetList.appendChild(tweetElement);
        });
        
        // Set up "View All" button
        template.querySelector('.view-all-btn').addEventListener('click', () => {
            showAllTweets(search);
        });
        
        return template;
    }
    
    function createTweetElement(tweet) {
        const template = tweetTemplate.content.cloneNode(true);
        
        // Set username
        template.querySelector('.username').textContent = tweet.username;
        
        // Set relevancy badge
        const relevancyBadge = template.querySelector('.relevancy-badge');
        relevancyBadge.textContent = `${tweet.relevancy_score}%`;
        
        // Apply color class based on relevancy
        if (tweet.relevancy_score >= 75) {
            relevancyBadge.classList.add('high-relevance');
        } else if (tweet.relevancy_score >= 50) {
            relevancyBadge.classList.add('medium-relevance');
        } else {
            relevancyBadge.classList.add('low-relevance');
        }
        
        // Set tweet content (truncated for card view)
        const content = tweet.text.length > 100 ? tweet.text.substring(0, 100) + '...' : tweet.text;
        template.querySelector('.tweet-content').textContent = content;
        
        // Set tweet link
        const tweetLink = template.querySelector('.tweet-link');
        if (tweet.tweet_url) {
            tweetLink.href = tweet.tweet_url;
        } else {
            // Fallback if URL not available
            tweetLink.href = `https://twitter.com/i/web/status/${tweet.id}`;
        }
        
        // Set date if available
        if (tweet.timestamp) {
            const tweetDate = new Date(tweet.timestamp);
            template.querySelector('.tweet-date').textContent = tweetDate.toLocaleString();
        } else {
            template.querySelector('.tweet-date').textContent = '';
        }
        
        // Add click event to show full tweet detail
        const tweetElement = template.querySelector('.tweet');
        tweetElement.addEventListener('click', (e) => {
            // If clicking the link itself, don't show detail view (let browser handle the link)
            if (!e.target.closest('.tweet-link')) {
                e.preventDefault();
                showTweetDetail(tweet);
            }
        });
        
        return template;
    }
    
    function showTweetDetail(tweet) {
        // Create detailed view of the tweet
        let detailHTML = `
            <div class="tweet-detail">
                <div class="tweet-header">
                    <h2 class="username">${tweet.username}</h2>
                    <span class="relevancy-badge ${getRelevancyClass(tweet.relevancy_score)}">
                        ${tweet.relevancy_score}% Relevant
                    </span>
                </div>
                <div class="tweet-content-full">
                    ${tweet.text}
                </div>
                <div class="tweet-images">
                    ${tweet.images && tweet.images.length > 0 ? 
                        tweet.images.map(img => `<img src="${img}" alt="Tweet image">`).join('') : 
                        ''}
                </div>
                <div class="hashtags">
                    ${tweet.hashtags && tweet.hashtags.length > 0 ? 
                        tweet.hashtags.map(tag => `<span class="hashtag">${tag}</span>`).join(' ') : 
                        ''}
                </div>
                <div class="tweet-footer">
                    ${tweet.timestamp ? `<span class="tweet-date">Posted on ${new Date(tweet.timestamp).toLocaleString()}</span>` : ''}
                    <a href="${tweet.tweet_url || `https://twitter.com/i/web/status/${tweet.id}`}" class="tweet-link-big" target="_blank">
                        <i class="fab fa-twitter"></i> View on Twitter
                    </a>
                </div>
            </div>
        `;
        
        tweetDetailContent.innerHTML = detailHTML;
        tweetDetailContainer.style.display = 'flex';
        document.body.style.overflow = 'hidden'; // Prevent scrolling behind modal
    }
    
    function closeTweetDetail() {
        tweetDetailContainer.style.display = 'none';
        document.body.style.overflow = ''; // Restore scrolling
    }
    
    function showAllTweets(search) {
        // Create detailed view with all tweets from the search
        let detailHTML = `
            <div class="all-tweets-detail">
                <h2>Search Results: ${search.term}</h2>
                <div class="search-meta">
                    <span class="search-date">Searched on ${new Date(search.date).toLocaleString()}</span>
                    <span class="relevancy-score ${getRelevancyClass(search.trendRelevancy)}">
                        ${search.trendRelevancy}% Trend Relevancy
                    </span>
                </div>
                <div class="tweet-list-full">
                    ${search.tweets.map(tweet => `
                        <div class="tweet tweet-full">
                            <div class="tweet-header">
                                <h3 class="username">${tweet.username}</h3>
                                <span class="relevancy-badge ${getRelevancyClass(tweet.relevancy_score)}">
                                    ${tweet.relevancy_score}% Relevant
                                </span>
                            </div>
                            <div class="tweet-content-full">
                                ${tweet.text}
                            </div>
                            <div class="tweet-footer">
                                ${tweet.timestamp ? `<span class="tweet-date">Posted on ${new Date(tweet.timestamp).toLocaleString()}</span>` : ''}
                                <a href="${tweet.tweet_url || `https://twitter.com/i/web/status/${tweet.id}`}" class="tweet-link" target="_blank">
                                    <i class="fab fa-twitter"></i> View on Twitter
                                </a>
                            </div>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
        
        tweetDetailContent.innerHTML = detailHTML;
        tweetDetailContainer.style.display = 'flex';
        document.body.style.overflow = 'hidden'; // Prevent scrolling behind modal
    }
    
    function getRelevancyClass(score) {
        if (score >= 75) return 'high-relevance';
        if (score >= 50) return 'medium-relevance';
        return 'low-relevance';
    }
    
    function goToPrevPage() {
        if (currentPage > 0) {
            currentPage--;
            displaySearchResults();
        }
    }
    
    function goToNextPage() {
        if (currentPage < totalPages - 1) {
            currentPage++;
            displaySearchResults();
        }
    }
    
    function updateSliderPosition() {
        // Calculate and apply transform to position the slider at the current page
        const transform = `translateX(-${currentPage * 100}%)`;
        searchResultsSlider.style.transform = transform;
    }
    
    // Local Storage functions
    function saveSearchHistory() {
        // Limit to most recent 30 searches to prevent excessive storage use
        const limitedHistory = searchHistory.slice(0, 30);
        localStorage.setItem('twitterAnalysisSearchHistory', JSON.stringify(limitedHistory));
    }
    
    function loadSearchHistory() {
        try {
            const saved = localStorage.getItem('twitterAnalysisSearchHistory');
            return saved ? JSON.parse(saved) : [];
        } catch (error) {
            console.error('Error loading search history:', error);
            return [];
        }
    }
});
