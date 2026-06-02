/**
 * TwitLysis v2.0 — Frontend Controller
 * Handles sidebar navigation, SSE search streaming, tweet rendering with links,
 * engagement display, Chart.js lifecycle management, and memory cleanup.
 */
document.addEventListener('DOMContentLoaded', function () {

    // =========================================================================
    // DOM References
    // =========================================================================
    const searchQueryInput = document.getElementById('search-query');
    const searchButton = document.getElementById('search-button');
    const searchStatus = document.getElementById('search-status');
    const liveOutput = document.getElementById('live-output');
    const progressContainer = document.getElementById('progress-container');
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress-text');
    const resultsList = document.getElementById('results-list');
    const navItems = document.querySelectorAll('.nav-item');

    // Chart instance registry (destroy before re-create to prevent memory leaks)
    const chartInstances = {};

    // Active EventSource reference (close on completion to prevent leaks)
    let activeEventSource = null;

    // =========================================================================
    // Sidebar Panel Navigation
    // =========================================================================
    navItems.forEach(item => {
        item.addEventListener('click', () => {
            const panelId = item.dataset.panel;
            if (panelId) switchPanel(panelId);
        });
    });

    function switchPanel(panelId) {
        // Update nav items
        navItems.forEach(item => {
            item.classList.toggle('active', item.dataset.panel === panelId);
        });
        // Update panels
        document.querySelectorAll('.panel').forEach(panel => {
            panel.classList.toggle('active', panel.id === panelId);
        });
    }

    // =========================================================================
    // Search — Enter Key Support
    // =========================================================================
    searchQueryInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !searchButton.disabled) {
            startSearch();
        }
    });

    searchButton.addEventListener('click', startSearch);

    // =========================================================================
    // Search — SSE Streaming
    // =========================================================================
    function startSearch() {
        const query = searchQueryInput.value.trim();
        if (!query) {
            searchStatus.textContent = 'Please enter a search term';
            searchStatus.className = 'search-status error';
            return;
        }

        // Close any existing EventSource
        if (activeEventSource) {
            activeEventSource.close();
            activeEventSource = null;
        }

        // Reset UI
        searchStatus.textContent = '';
        searchStatus.className = 'search-status';
        liveOutput.innerHTML = '';
        progressContainer.style.display = 'block';
        progressBar.style.width = '0%';
        progressText.textContent = 'Starting...';
        searchButton.disabled = true;

        // Ensure we're on the search panel
        switchPanel('search-panel');

        // Start SSE connection
        activeEventSource = new EventSource(`/api/search?query=${encodeURIComponent(query)}`);

        activeEventSource.onmessage = function (event) {
            try {
                const data = JSON.parse(event.data);

                // Handle error
                if (data.error) {
                    appendOutput(data.message, 'error');
                    searchStatus.textContent = 'Error occurred during analysis';
                    searchStatus.className = 'search-status error';
                    progressContainer.style.display = 'none';
                    searchButton.disabled = false;
                    closeEventSource();
                    return;
                }

                // Update progress
                if (data.progress !== undefined) {
                    progressBar.style.width = `${data.progress}%`;
                    progressText.textContent = `${data.progress}% Complete`;
                }

                // Display message
                if (data.message) {
                    let cls = 'log';
                    if (data.message.includes('[ERROR]') || data.message.includes('[CRITICAL]')) cls = 'error';
                    else if (data.message.includes('[WARNING]')) cls = 'warning';
                    else if (data.message.includes('[INFO]') || data.message.includes('[COMPLETE]') || data.message.includes('[RESULTS]')) cls = 'info';
                    else if (data.message.includes('[STEP')) cls = 'success';

                    appendOutput(data.message, cls);
                }

                // Check for completion
                if (data.progress === 100 || (data.message && data.message.includes('[COMPLETE]'))) {
                    finishSearch(query);
                }

            } catch (e) {
                console.error('SSE parse error:', e);
                appendOutput('[ERROR] Communication error with server', 'error');
            }
        };

        activeEventSource.onerror = function () {
            appendOutput('[ERROR] Connection to server lost', 'error');
            searchStatus.textContent = 'Connection error';
            searchStatus.className = 'search-status error';
            progressContainer.style.display = 'none';
            searchButton.disabled = false;
            closeEventSource();
        };
    }

    function closeEventSource() {
        if (activeEventSource) {
            activeEventSource.close();
            activeEventSource = null;
        }
    }

    function appendOutput(text, cls) {
        const line = document.createElement('p');
        line.className = `output-line ${cls}`;
        line.textContent = text;
        liveOutput.appendChild(line);
        liveOutput.scrollTop = liveOutput.scrollHeight;
    }

    function finishSearch(query) {
        searchButton.disabled = false;
        searchStatus.textContent = 'Analysis complete!';
        searchStatus.className = 'search-status success';
        progressText.textContent = 'Complete';
        progressBar.style.width = '100%';
        closeEventSource();

        // Refresh data and navigate to results
        setTimeout(() => {
            loadPreviousResults();
            loadTrends();
            loadHashtags();

            setTimeout(() => {
                progressContainer.style.display = 'none';
                switchPanel('results-panel');
            }, 1500);
        }, 800);
    }

    // =========================================================================
    // Load Previous Results
    // =========================================================================
    function loadPreviousResults() {
        fetch('/api/previous-results')
            .then(r => r.json())
            .then(data => {
                resultsList.innerHTML = '';

                if (!data.length) {
                    resultsList.innerHTML = '<p class="no-results">No previous results found. Run a search to get started.</p>';
                    return;
                }

                const frag = document.createDocumentFragment();
                data.forEach(result => {
                    const card = document.createElement('div');
                    card.className = 'result-card';
                    card.innerHTML = `
                        <h3>${escapeHtml(result.term)}</h3>
                        <div class="result-meta">
                            <span><i class="fas fa-chart-line"></i> Score: ${result.score}</span>
                            <span><i class="fas fa-comment"></i> ${result.tweet_count} tweets</span>
                            <span><i class="fas fa-calendar"></i> ${result.date}</span>
                        </div>
                        <button class="view-btn" data-term="${escapeHtml(result.term)}">View Details</button>
                    `;
                    frag.appendChild(card);

                    card.querySelector('.view-btn').addEventListener('click', () => {
                        document.getElementById('term-select').value = result.term;
                        loadTermDetails(result.term);
                        switchPanel('trends-panel');
                    });
                });
                resultsList.appendChild(frag);

                // Update term selector
                updateTermSelector(data.map(r => r.term));
            })
            .catch(err => {
                console.error('Error loading results:', err);
                resultsList.innerHTML = '<p class="no-results">Failed to load previous results</p>';
            });
    }

    // =========================================================================
    // Term Selector
    // =========================================================================
    function updateTermSelector(terms) {
        const sel = document.getElementById('term-select');
        const current = sel.value;

        // Clear existing options except default
        while (sel.options.length > 1) sel.remove(1);

        terms.forEach(term => {
            const opt = document.createElement('option');
            opt.value = term;
            opt.textContent = term;
            sel.appendChild(opt);
        });

        if (current && terms.includes(current)) sel.value = current;

        // Attach listener once
        if (!sel._hasListener) {
            sel.addEventListener('change', () => {
                if (sel.value) {
                    loadTermDetails(sel.value);
                } else {
                    document.getElementById('selected-term-details').style.display = 'none';
                    document.getElementById('no-term-selected').style.display = 'block';
                }
            });
            sel._hasListener = true;
        }
    }

    // =========================================================================
    // Term Details (Sentiment + Top Tweets)
    // =========================================================================
    function loadTermDetails(term) {
        document.getElementById('selected-term-details').style.display = 'none';
        document.getElementById('no-term-selected').style.display = 'none';

        fetch(`/api/term-details?term=${encodeURIComponent(term)}`)
            .then(r => r.json())
            .then(data => {
                if (data.error) {
                    console.error('Term details error:', data.error);
                    return;
                }

                document.getElementById('selected-term-details').style.display = 'block';
                document.getElementById('no-term-selected').style.display = 'none';

                // Sentiment chart
                renderSentimentChart('selected-sentiment-chart', data.sentiment);

                // Signal strength badge
                const badge = document.getElementById('signal-strength-badge');
                if (data.sentiment && data.sentiment.signal_strength && data.sentiment.signal_strength !== 'none') {
                    const strength = data.sentiment.signal_strength;
                    const compound = data.sentiment.avg_compound || 0;
                    const direction = compound >= 0 ? 'Positive' : 'Negative';
                    badge.className = `signal-badge ${strength}`;
                    badge.innerHTML = `<i class="fas fa-signal"></i> ${capitalize(strength)} ${direction} Signal (${compound > 0 ? '+' : ''}${compound})`;
                } else {
                    badge.className = 'signal-badge none';
                    badge.innerHTML = '';
                }

                // Tweets
                const tweetsContainer = document.getElementById('selected-tweets');
                tweetsContainer.innerHTML = '';

                if (data.tweets && data.tweets.length > 0) {
                    const frag = document.createDocumentFragment();
                    data.tweets.forEach(tweet => {
                        frag.appendChild(createTweetElement(tweet));
                    });
                    tweetsContainer.appendChild(frag);
                } else {
                    tweetsContainer.innerHTML = '<p class="no-results">No tweets found</p>';
                }
            })
            .catch(err => console.error('Error loading term details:', err));
    }

    // =========================================================================
    // Tweet Element Builder
    // =========================================================================
    function createTweetElement(tweet) {
        const el = document.createElement('div');
        el.className = 'tweet';

        const username = tweet.username || 'unknown';
        const score = tweet.relevancy_score || 0;
        const text = tweet.text || '';
        const url = tweet.tweet_url || '';
        const eng = tweet.engagement || {};

        let linkHtml = '';
        if (url) {
            linkHtml = `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" class="tweet-link"><i class="fas fa-external-link-alt"></i> View on X</a>`;
        }

        let engHtml = '';
        if (eng.replies || eng.retweets || eng.likes) {
            engHtml = `
                <div class="tweet-engagement">
                    <span><i class="fas fa-reply"></i> ${formatNum(eng.replies || 0)}</span>
                    <span><i class="fas fa-retweet"></i> ${formatNum(eng.retweets || 0)}</span>
                    <span><i class="fas fa-heart"></i> ${formatNum(eng.likes || 0)}</span>
                </div>
            `;
        }

        el.innerHTML = `
            <p class="tweet-text">${escapeHtml(text)}</p>
            <div class="tweet-meta">
                <span class="tweet-username">${escapeHtml(username)}</span>
                <span class="tweet-score">Relevancy: ${score}%</span>
                ${linkHtml}
            </div>
            ${engHtml}
        `;
        return el;
    }

    // =========================================================================
    // Trends
    // =========================================================================
    function loadTrends() {
        fetch('/api/trends')
            .then(r => r.json())
            .then(data => {
                const list = document.getElementById('top-trends-list');
                list.innerHTML = '';

                if (data.top_trends && data.top_trends.length > 0) {
                    data.top_trends.forEach(trend => {
                        const li = document.createElement('li');
                        li.innerHTML = `
                            <span class="trend-name">${escapeHtml(trend.term)}</span>
                            <span class="trend-count">${trend.count} tweets</span>
                        `;
                        li.addEventListener('click', () => {
                            document.getElementById('term-select').value = trend.term;
                            loadTermDetails(trend.term);
                            switchPanel('trends-panel');
                        });
                        list.appendChild(li);
                    });
                } else {
                    list.innerHTML = '<li class="no-results">No trends data available yet</li>';
                }
            })
            .catch(err => console.error('Error loading trends:', err));
    }

    // =========================================================================
    // Hashtags
    // =========================================================================
    function loadHashtags() {
        fetch('/api/hashtags')
            .then(r => r.json())
            .then(data => {
                if (data.hashtags && data.hashtags.length > 0) {
                    renderHashtagCloud(data.hashtags);
                    renderHashtagChart(data.hashtags.slice(0, 10));
                } else {
                    document.getElementById('hashtag-cloud').innerHTML = '<p class="no-results">No hashtags data available</p>';
                }
            })
            .catch(err => console.error('Error loading hashtags:', err));
    }

    function renderHashtagCloud(hashtags) {
        const container = document.getElementById('hashtag-cloud');
        container.innerHTML = '';
        const frag = document.createDocumentFragment();

        hashtags.forEach(hashtag => {
            const tag = document.createElement('span');
            tag.className = 'hashtag';
            tag.textContent = hashtag.text;
            tag.style.fontSize = `${Math.max(0.8, Math.min(2.2, 0.9 + (hashtag.count / 8) * 0.15))}em`;
            tag.addEventListener('click', () => {
                searchQueryInput.value = hashtag.text;
                switchPanel('search-panel');
                startSearch();
            });
            frag.appendChild(tag);
        });
        container.appendChild(frag);
    }

    // =========================================================================
    // Chart.js — Managed Lifecycle
    // =========================================================================
    function destroyChart(key) {
        if (chartInstances[key]) {
            chartInstances[key].destroy();
            delete chartInstances[key];
        }
    }

    function renderSentimentChart(canvasId, sentimentData) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;

        destroyChart(canvasId);

        chartInstances[canvasId] = new Chart(canvas, {
            type: 'doughnut',
            data: {
                labels: ['Positive', 'Neutral', 'Negative'],
                datasets: [{
                    data: [
                        sentimentData.positive || 0,
                        sentimentData.neutral || 0,
                        sentimentData.negative || 0
                    ],
                    backgroundColor: ['#00ba7c', '#ffad1f', '#f4212e'],
                    borderWidth: 0,
                    hoverOffset: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '65%',
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            color: '#8899a6',
                            padding: 16,
                            font: { family: "'Inter', sans-serif", size: 12 }
                        }
                    }
                }
            }
        });
    }

    function renderHashtagChart(hashtags) {
        const canvas = document.getElementById('hashtag-chart');
        if (!canvas) return;

        destroyChart('hashtag-chart');

        chartInstances['hashtag-chart'] = new Chart(canvas, {
            type: 'bar',
            data: {
                labels: hashtags.map(h => h.text),
                datasets: [{
                    label: 'Mentions',
                    data: hashtags.map(h => h.count),
                    backgroundColor: 'rgba(29, 161, 242, 0.6)',
                    borderColor: '#1da1f2',
                    borderWidth: 1,
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        ticks: { color: '#8899a6', font: { family: "'Inter', sans-serif", size: 11 } },
                        grid: { color: 'rgba(47, 51, 54, 0.5)' }
                    },
                    y: {
                        beginAtZero: true,
                        ticks: { color: '#8899a6', font: { family: "'Inter', sans-serif", size: 11 } },
                        grid: { color: 'rgba(47, 51, 54, 0.5)' }
                    }
                },
                plugins: {
                    legend: { display: false }
                }
            }
        });
    }

    // =========================================================================
    // Utilities
    // =========================================================================
    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function capitalize(s) {
        return s ? s.charAt(0).toUpperCase() + s.slice(1) : '';
    }

    function formatNum(n) {
        if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
        if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
        return String(n);
    }

    // =========================================================================
    // Initial Load
    // =========================================================================
    loadPreviousResults();
    loadTrends();
    loadHashtags();
});
