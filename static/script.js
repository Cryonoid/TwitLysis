document.addEventListener('DOMContentLoaded', function() {
    // DOM elements
    const searchQueryInput = document.getElementById('search-query');
    const searchButton = document.getElementById('search-button');
    const searchStatus = document.getElementById('search-status');
    const liveOutput = document.getElementById('live-output');
    const progressContainer = document.getElementById('progress-container');
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress-text');
    const resultsList = document.getElementById('results-list');
    const tabButtons = document.querySelectorAll('.tab-button');
    const tabContents = document.querySelectorAll('.tab-content');
    
    // Event listeners
    searchButton.addEventListener('click', startSearch);
    tabButtons.forEach(button => {
        button.addEventListener('click', () => switchTab(button.dataset.tab));
    });
    
    // Load initial data
    loadPreviousResults();
    loadTrends();
    loadHashtags();
    
    // Functions
    function startSearch() {
        const query = searchQueryInput.value.trim();
        if (!query) {
            searchStatus.textContent = "Please enter a search term";
            searchStatus.classList.add('error');
            return;
        }
        
        // Reset UI
        searchStatus.textContent = "";
        searchStatus.classList.remove('error');
        liveOutput.innerHTML = '<p class="info-message">Starting analysis...</p>';
        progressContainer.style.display = 'block';
        progressBar.style.width = '0%';
        progressText.textContent = 'Starting...';
        searchButton.disabled = true;
        
        // Start EventSource for SSE
        const eventSource = new EventSource(`/api/search?query=${encodeURIComponent(query)}`);
        
        eventSource.onmessage = function(event) {
            try {
                const data = JSON.parse(event.data);
                
                // Handle error messages
                if (data.error) {
                    liveOutput.innerHTML += `<p class="error-message">${data.message}</p>`;
                    searchStatus.textContent = "Error occurred during analysis";
                    searchStatus.classList.add('error');
                    progressContainer.style.display = 'none';
                    searchButton.disabled = false;
                    eventSource.close();
                    return;
                }
                
                // Update progress bar
                if (data.progress !== undefined) {
                    progressBar.style.width = `${data.progress}%`;
                    progressText.textContent = `${data.progress}% Complete`;
                }
                
                // Format and display message
                if (data.message) {
                    // Format message based on content
                    let messageClass = 'log-message';
                    if (data.message.includes('[ERROR]')) {
                        messageClass = 'error-message';
                    } else if (data.message.includes('[WARNING]')) {
                        messageClass = 'warning-message';
                    } else if (data.message.includes('[INFO]') || data.message.includes('[COMPLETE]')) {
                        messageClass = 'info-message';
                    }
                    
                    liveOutput.innerHTML += `<p class="${messageClass}">${data.message}</p>`;
                    liveOutput.scrollTop = liveOutput.scrollHeight; // Auto-scroll to bottom
                }
                
                // Check for completion
                if (data.progress === 100 || data.message.includes('[COMPLETE]')) {
                    finishSearch(query);
                }
                
            } catch (e) {
                console.error('Error parsing SSE message:', e);
                liveOutput.innerHTML += `<p class="error-message">[ERROR] Communication error with server</p>`;
            }
        };
        
        eventSource.onerror = function() {
            liveOutput.innerHTML += `<p class="error-message">[ERROR] Connection to server lost</p>`;
            searchStatus.textContent = "Connection error";
            searchStatus.classList.add('error');
            progressContainer.style.display = 'none';
            searchButton.disabled = false;
            eventSource.close();
        };
    }
    
    function finishSearch(query) {
        // Enable search button
        searchButton.disabled = false;
        
        // Update status
        searchStatus.textContent = "Analysis complete!";
        searchStatus.classList.add('success');
        
        // Update progress
        progressText.textContent = "Complete";
        progressBar.style.width = "100%";
        
        // Refresh results list with a slight delay
        setTimeout(() => {
            loadPreviousResults();
            loadTrends();
            loadHashtags();
            
            // Remove progress bar after a delay
            setTimeout(() => {
                progressContainer.style.display = 'none';
            }, 2000);
        }, 1000);
    }
    
    function switchTab(tabId) {
        tabButtons.forEach(button => {
            button.classList.toggle('active', button.dataset.tab === tabId);
        });
        
        tabContents.forEach(content => {
            content.classList.toggle('active', content.id === tabId);
        });
    }
    
    function loadPreviousResults() {
        fetch('/api/previous-results')
            .then(response => response.json())
            .then(data => {
                resultsList.innerHTML = '';
                
                if (data.length === 0) {
                    resultsList.innerHTML = '<p class="no-results">No previous results found</p>';
                    return;
                }
                
                data.forEach(result => {
                    const resultItem = document.createElement('div');
                    resultItem.className = 'result-item';
                    resultItem.innerHTML = `
                        <h3>${result.term}</h3>
                        <div class="result-meta">
                            <span><i class="fas fa-chart-line"></i> Score: ${result.score}</span>
                            <span><i class="fas fa-comment"></i> Tweets: ${result.tweet_count}</span>
                            <span><i class="fas fa-calendar"></i> ${result.date}</span>
                        </div>
                        <button class="view-button" data-term="${result.term}">View Details</button>
                    `;
                    resultsList.appendChild(resultItem);
                    
                    // Add event listener to view button
                    resultItem.querySelector('.view-button').addEventListener('click', () => {
                        document.getElementById('term-select').value = result.term;
                        loadTermDetails(result.term);
                        switchTab('selected-tab');
                    });
                });
                
                // Update term selector
                updateTermSelector(data.map(r => r.term));
            })
            .catch(error => {
                console.error('Error loading previous results:', error);
                resultsList.innerHTML = '<p class="error-message">Failed to load previous results</p>';
            });
    }
    
    function updateTermSelector(terms) {
        const termSelect = document.getElementById('term-select');
        const currentSelection = termSelect.value;
        
        // Clear existing options except the default one
        while (termSelect.options.length > 1) {
            termSelect.remove(1);
        }
        
        // Add new terms
        terms.forEach(term => {
            const option = document.createElement('option');
            option.value = term;
            option.textContent = term;
            termSelect.appendChild(option);
        });
        
        // Restore selection if possible
        if (currentSelection && terms.includes(currentSelection)) {
            termSelect.value = currentSelection;
        }
        
        // Add change event listener
        if (!termSelect.hasEventListener) {
            termSelect.addEventListener('change', () => {
                const selectedTerm = termSelect.value;
                if (selectedTerm) {
                    loadTermDetails(selectedTerm);
                } else {
                    document.getElementById('selected-term-details').style.display = 'none';
                    document.getElementById('no-term-selected').style.display = 'block';
                }
            });
            termSelect.hasEventListener = true;
        }
    }
    
    function loadTermDetails(term) {
        document.getElementById('selected-term-details').style.display = 'none';
        document.getElementById('no-term-selected').style.display = 'none';
        
        fetch(`/api/term-details?term=${encodeURIComponent(term)}`)
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    console.error('Error loading term details:', data.error);
                    return;
                }
                
                // Display term details
                document.getElementById('selected-term-details').style.display = 'block';
                document.getElementById('no-term-selected').style.display = 'none';
                
                // Render sentiment chart
                renderSentimentChart('selected-sentiment-chart', data.sentiment);
                
                // Render top tweets
                const tweetsContainer = document.getElementById('selected-tweets');
                tweetsContainer.innerHTML = '';
                
                if (data.tweets && data.tweets.length > 0) {
                    data.tweets.forEach(tweet => {
                        const tweetElement = document.createElement('div');
                        tweetElement.className = 'tweet';
                        tweetElement.innerHTML = `
                            <p class="tweet-text">${tweet.text}</p>
                            <div class="tweet-meta">
                                <span class="tweet-username">@${tweet.username || 'unknown'}</span>
                                <span class="tweet-score">Relevancy: ${tweet.relevancy_score}%</span>
                            </div>
                        `;
                        tweetsContainer.appendChild(tweetElement);
                    });
                } else {
                    tweetsContainer.innerHTML = '<p class="no-results">No tweets found</p>';
                }
            })
            .catch(error => {
                console.error('Error loading term details:', error);
            });
    }
    
    function loadTrends() {
        fetch('/api/trends')
            .then(response => response.json())
            .then(data => {
                const topTrendsList = document.getElementById('top-trends-list');
                topTrendsList.innerHTML = '';
                
                if (data.top_trends && data.top_trends.length > 0) {
                    data.top_trends.forEach(trend => {
                        const trendItem = document.createElement('li');
                        trendItem.innerHTML = `
                            <span class="trend-name">${trend.term}</span>
                            <span class="trend-count">${trend.count} tweets</span>
                        `;
                        trendItem.addEventListener('click', () => {
                            document.getElementById('term-select').value = trend.term;
                            loadTermDetails(trend.term);
                            switchTab('selected-tab');
                        });
                        topTrendsList.appendChild(trendItem);
                    });
                } else {
                    topTrendsList.innerHTML = '<li class="no-trends">No trends data available</li>';
                }
            })
            .catch(error => {
                console.error('Error loading trends:', error);
            });
    }
    
    function loadHashtags() {
        fetch('/api/hashtags')
            .then(response => response.json())
            .then(data => {
                if (data.hashtags && data.hashtags.length > 0) {
                    renderHashtagCloud(data.hashtags);
                    renderHashtagChart(data.hashtags.slice(0, 10));
                } else {
                    document.getElementById('hashtag-cloud').innerHTML = '<p class="no-results">No hashtags data available</p>';
                    document.getElementById('hashtag-chart').innerHTML = '<p class="no-results">No hashtags data available</p>';
                }
            })
            .catch(error => {
                console.error('Error loading hashtags:', error);
            });
    }
    
    function renderSentimentChart(canvasId, sentimentData) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;
        
        // Destroy existing chart if it exists
        if (canvas.chart) {
            canvas.chart.destroy();
        }
        
        // Create new chart
        canvas.chart = new Chart(canvas, {
            type: 'doughnut',
            data: {
                labels: ['Positive', 'Neutral', 'Negative'],
                datasets: [{
                    data: [
                        sentimentData.positive || 0,
                        sentimentData.neutral || 0,
                        sentimentData.negative || 0
                    ],
                    backgroundColor: [
                        '#4caf50', // Green for positive
                        '#ff9800', // Orange for neutral
                        '#f44336'  // Red for negative
                    ]
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            color: '#e0e0e0'
                        }
                    }
                }
            }
        });
    }
    
    function renderHashtagCloud(hashtags) {
        const container = document.getElementById('hashtag-cloud');
        container.innerHTML = '';
        
        hashtags.forEach(hashtag => {
            const tag = document.createElement('span');
            tag.className = 'hashtag';
            tag.textContent = hashtag.text;
            tag.style.fontSize = `${Math.max(0.8, Math.min(2.5, 1 + (hashtag.count / 5) * 0.1))}em`;
            tag.addEventListener('click', () => {
                searchQueryInput.value = hashtag.text;
                startSearch();
            });
            container.appendChild(tag);
        });
    }
    
    function renderHashtagChart(hashtags) {
        const canvas = document.getElementById('hashtag-chart');
        if (!canvas) return;
        
        // Destroy existing chart if it exists
        if (canvas.chart) {
            canvas.chart.destroy();
        }
        
        // Create new chart
        canvas.chart = new Chart(canvas, {
            type: 'bar',
            data: {
                labels: hashtags.map(h => h.text),
                datasets: [{
                    label: 'Tweet Count',
                    data: hashtags.map(h => h.count),
                    backgroundColor: '#1da1f2',
                    borderColor: '#0d8ecf',
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                scales: {
                    x: {
                        ticks: {
                            color: '#e0e0e0'
                        },
                        grid: {
                            color: '#333'
                        }
                    },
                    y: {
                        beginAtZero: true,
                        ticks: {
                            color: '#e0e0e0'
                        },
                        grid: {
                            color: '#333'
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: false
                    }
                }
            }
        });
    }
});
