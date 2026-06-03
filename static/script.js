/**
 * TwitLysis v2.1 — Frontend Controller
 * Handles sidebar navigation, step timeline search UI, SSE streaming,
 * enriched trend/result cards, hashtag cloud, Chart.js lifecycle, and memory cleanup.
 */
document.addEventListener('DOMContentLoaded', function () {

    // =========================================================================
    // DOM References
    // =========================================================================
    const searchQueryInput = document.getElementById('search-query');
    const searchButton = document.getElementById('search-button');
    const searchStatus = document.getElementById('search-status');
    const liveOutput = document.getElementById('live-output');
    const stepTimeline = document.getElementById('step-timeline');
    const stepProgress = document.getElementById('step-progress');
    const rawLogToggle = document.getElementById('raw-log-toggle');
    const rawLogContainer = document.getElementById('raw-log-container');
    const resultsList = document.getElementById('results-list');
    const navItems = document.querySelectorAll('.nav-item');

    // Chart instance registry (destroy before re-create to prevent memory leaks)
    const chartInstances = {};

    // Active EventSource reference (close on completion to prevent leaks)
    let activeEventSource = null;

    // Step timeline state
    const STEP_LABELS = [
        'Scraping & Deduplicating',
        'Saving Raw Tweets',
        'Calculating Relevancy',
        'Sorting Results',
        'Saving Results'
    ];
    let currentStepCards = [];
    let currentStepNum = 0;

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
        navItems.forEach(item => {
            item.classList.toggle('active', item.dataset.panel === panelId);
        });
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
    // Raw Log Toggle
    // =========================================================================
    rawLogToggle.addEventListener('click', () => {
        const isCollapsed = rawLogContainer.classList.contains('collapsed');
        rawLogContainer.classList.toggle('collapsed', !isCollapsed);
        rawLogToggle.classList.toggle('expanded', isCollapsed);
        rawLogToggle.querySelector('span').textContent = isCollapsed ? 'Hide raw log' : 'Show raw log';
    });

    // =========================================================================
    // Step Timeline — Helpers
    // =========================================================================
    function resetTimeline() {
        stepTimeline.innerHTML = '';
        currentStepCards = [];
        currentStepNum = 0;

        // Reset segmented progress
        stepProgress.style.display = 'flex';
        document.querySelectorAll('.step-segment').forEach(seg => {
            seg.className = 'step-segment';
        });

        // Reset raw log
        liveOutput.innerHTML = '';
        rawLogToggle.style.display = 'flex';
        rawLogContainer.classList.add('collapsed');
        rawLogToggle.classList.remove('expanded');
        rawLogToggle.querySelector('span').textContent = 'Show raw log';
    }

    function createStepCard(stepNum, title) {
        const card = document.createElement('div');
        card.className = 'step-card';
        card.id = `step-card-${stepNum}`;
        card.innerHTML = `
            <div class="step-card-header">
                <div class="step-badge running">${stepNum}</div>
                <span class="step-title">${escapeHtml(title)}</span>
                <div class="step-spinner"></div>
            </div>
            <div class="step-details"></div>
        `;
        stepTimeline.appendChild(card);
        currentStepCards.push(card);

        // Update segmented progress
        const segment = document.querySelector(`.step-segment[data-step="${stepNum}"]`);
        if (segment) {
            segment.classList.add('active');
            // Mark previous segments as done
            for (let i = 1; i < stepNum; i++) {
                const prev = document.querySelector(`.step-segment[data-step="${i}"]`);
                if (prev) {
                    prev.classList.remove('active');
                    prev.classList.add('done');
                    prev.querySelector('span').innerHTML = '<i class="fas fa-check" style="font-size:10px"></i>';
                }
            }
        }

        return card;
    }

    function markStepDone(stepNum) {
        const card = document.getElementById(`step-card-${stepNum}`);
        if (!card) return;
        const badge = card.querySelector('.step-badge');
        const spinner = card.querySelector('.step-spinner');
        if (badge) {
            badge.className = 'step-badge done';
            badge.innerHTML = '<i class="fas fa-check" style="font-size:12px"></i>';
        }
        if (spinner) {
            spinner.outerHTML = '<i class="fas fa-check step-check"></i>';
        }

        // Update segment
        const segment = document.querySelector(`.step-segment[data-step="${stepNum}"]`);
        if (segment) {
            segment.classList.remove('active');
            segment.classList.add('done');
            segment.querySelector('span').innerHTML = '<i class="fas fa-check" style="font-size:10px"></i>';
        }
    }

    function markStepError(stepNum) {
        const card = document.getElementById(`step-card-${stepNum}`);
        if (!card) return;
        const badge = card.querySelector('.step-badge');
        const spinner = card.querySelector('.step-spinner');
        if (badge) {
            badge.className = 'step-badge error';
            badge.innerHTML = '<i class="fas fa-times" style="font-size:12px"></i>';
        }
        if (spinner) {
            spinner.outerHTML = '<i class="fas fa-exclamation-triangle" style="color:var(--error);font-size:14px"></i>';
        }

        const segment = document.querySelector(`.step-segment[data-step="${stepNum}"]`);
        if (segment) {
            segment.classList.remove('active');
            segment.classList.add('error');
            segment.querySelector('span').innerHTML = '<i class="fas fa-times" style="font-size:10px"></i>';
        }
    }

    function appendToStep(stepNum, text, cls) {
        const card = document.getElementById(`step-card-${stepNum}`);
        if (!card) return;
        const details = card.querySelector('.step-details');
        const line = document.createElement('p');
        line.className = `step-detail-line ${cls}`;
        line.textContent = text;
        details.appendChild(line);
        details.scrollTop = details.scrollHeight;
    }

    function classifyMessage(msg) {
        if (msg.includes('[ERROR]') || msg.includes('[CRITICAL]')) return 'error';
        if (msg.includes('[WARNING]')) return 'warning';
        if (msg.includes('[INFO]') || msg.includes('[COMPLETE]') || msg.includes('[RESULTS]')) return 'info';
        if (msg.includes('[STEP')) return 'success';
        return 'log';
    }

    // =========================================================================
    // Search — SSE Streaming with Step Timeline
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
        searchButton.disabled = true;
        resetTimeline();

        // Ensure we're on the search panel
        switchPanel('search-panel');

        // Start SSE connection
        activeEventSource = new EventSource(`/api/search?query=${encodeURIComponent(query)}`);

        activeEventSource.onmessage = function (event) {
            try {
                const data = JSON.parse(event.data);

                // Handle error
                if (data.error) {
                    appendRawLog(data.message, 'error');
                    if (currentStepNum > 0) {
                        markStepError(currentStepNum);
                        appendToStep(currentStepNum, data.message, 'error');
                    }
                    searchStatus.textContent = 'Error occurred during analysis';
                    searchStatus.className = 'search-status error';
                    searchButton.disabled = false;
                    closeEventSource();
                    return;
                }

                const msg = data.message || '';

                // Detect step transitions
                if (msg.includes('[STEP ')) {
                    try {
                        const stepNum = parseInt(msg.split('[STEP ')[1].split('/')[0]);
                        if (stepNum > currentStepNum) {
                            // Mark previous step as done
                            if (currentStepNum > 0) {
                                markStepDone(currentStepNum);
                            }
                            currentStepNum = stepNum;
                            const label = STEP_LABELS[stepNum - 1] || `Step ${stepNum}`;
                            createStepCard(stepNum, label);
                        }
                    } catch (e) { /* ignore parse error */ }
                }

                // Append message to current step or create initial step
                if (msg) {
                    const cls = classifyMessage(msg);
                    appendRawLog(msg, cls);

                    if (currentStepNum > 0) {
                        // Skip the [STEP] line itself (it's the card title)
                        if (!msg.includes('[STEP ') && !msg.includes('[START]') && !msg.includes('[INFO] This may take')) {
                            appendToStep(currentStepNum, msg, cls);
                        }
                    }
                }

                // Check for completion
                if (data.progress === 100 || (msg && msg.includes('[COMPLETE]'))) {
                    if (currentStepNum > 0) {
                        markStepDone(currentStepNum);
                    }
                    finishSearch(query);
                }

            } catch (e) {
                console.error('SSE parse error:', e);
                appendRawLog('[ERROR] Communication error with server', 'error');
            }
        };

        activeEventSource.onerror = function () {
            appendRawLog('[ERROR] Connection to server lost', 'error');
            if (currentStepNum > 0) {
                markStepError(currentStepNum);
            }
            searchStatus.textContent = 'Connection error';
            searchStatus.className = 'search-status error';
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

    function appendRawLog(text, cls) {
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
        closeEventSource();

        // Refresh data in background so results/trends are ready when user navigates
        setTimeout(() => {
            loadPreviousResults();
            loadTrends();
        }, 800);
    }

    // =========================================================================
    // Load Previous Results (Enriched)
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

                    const score = result.score || 0;
                    const gaugeColor = score > 60 ? 'var(--success)' : score > 30 ? 'var(--warning)' : 'var(--error)';
                    const circumference = 2 * Math.PI * 18; // r=18
                    const offset = circumference - (score / 100) * circumference;

                    const sentimentDotClass = getSentimentDotClass(result.sentiment_signal, result.avg_compound);
                    const relativeTime = getRelativeTime(result.date);
                    const preview = result.top_tweet_preview || '';

                    card.innerHTML = `
                        <div class="result-card-top">
                            <div class="result-gauge">
                                <svg viewBox="0 0 44 44">
                                    <circle class="gauge-bg" cx="22" cy="22" r="18" />
                                    <circle class="gauge-fill" cx="22" cy="22" r="18"
                                        stroke="${gaugeColor}"
                                        stroke-dasharray="${circumference}"
                                        stroke-dashoffset="${offset}" />
                                </svg>
                                <div class="gauge-text">${score}</div>
                            </div>
                            <div class="result-card-info">
                                <h3>
                                    <span class="sentiment-dot ${sentimentDotClass}"></span>
                                    ${escapeHtml(result.term)}
                                </h3>
                                <div class="result-meta">
                                    <span><i class="fas fa-comment"></i> ${result.tweet_count} tweets</span>
                                    <span><i class="fas fa-clock"></i> ${relativeTime}</span>
                                </div>
                            </div>
                        </div>
                        ${preview ? `<p class="result-preview">"${escapeHtml(preview)}"</p>` : '<p class="result-preview" style="opacity:0.3">No tweet preview available</p>'}
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
    // Trends (Enriched Cards + Hashtag Cloud)
    // =========================================================================
    function loadTrends() {
        // Load trends and hashtags in parallel
        Promise.all([
            fetch('/api/trends').then(r => r.json()),
            fetch('/api/hashtags').then(r => r.json())
        ]).then(([trendData, hashtagData]) => {
            // Render enriched trend cards
            const container = document.getElementById('top-trends-list');
            container.innerHTML = '';

            if (trendData.top_trends && trendData.top_trends.length > 0) {
                const frag = document.createDocumentFragment();
                trendData.top_trends.forEach((trend, index) => {
                    const card = document.createElement('div');
                    card.className = 'trend-card';

                    const rank = index + 1;
                    const rankClass = rank <= 3 ? 'top-3' : 'regular';
                    const sentimentDotClass = getSentimentDotClass(trend.sentiment_signal, trend.avg_compound);
                    const hashtagPills = (trend.top_hashtags || []).slice(0, 3).map(
                        h => `<span class="hashtag-pill">${escapeHtml(h)}</span>`
                    ).join('');

                    card.innerHTML = `
                        <div class="trend-rank ${rankClass}">${rank}</div>
                        <div class="trend-card-body">
                            <div class="trend-card-title">
                                <span class="sentiment-dot ${sentimentDotClass}"></span>
                                ${escapeHtml(trend.term)}
                            </div>
                            <div class="trend-card-stats">
                                <span><i class="fas fa-comment"></i> ${trend.count} tweets</span>
                                <span><i class="fas fa-signal"></i> ${capitalize(trend.sentiment_signal || 'none')}</span>
                            </div>
                            ${hashtagPills ? `<div class="trend-hashtag-pills">${hashtagPills}</div>` : ''}
                        </div>
                    `;

                    card.addEventListener('click', () => {
                        document.getElementById('term-select').value = trend.term;
                        loadTermDetails(trend.term);
                        // Scroll to term analysis card
                        document.getElementById('term-analysis-card').scrollIntoView({ behavior: 'smooth', block: 'start' });
                    });

                    frag.appendChild(card);
                });
                container.appendChild(frag);
            } else {
                container.innerHTML = '<p class="no-results">No trends data available yet</p>';
            }

            // Render hashtag cloud (merged from former Hashtags panel)
            if (hashtagData.hashtags && hashtagData.hashtags.length > 0) {
                renderHashtagCloud(hashtagData.hashtags);
            } else {
                document.getElementById('hashtag-cloud').innerHTML = '<p class="no-results">No hashtags data available</p>';
            }
        }).catch(err => {
            console.error('Error loading trends:', err);
            document.getElementById('top-trends-list').innerHTML = '<p class="no-results">Failed to load trends</p>';
        });
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
                searchQueryInput.focus();
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

    function getSentimentDotClass(signal, compound) {
        if (!signal || signal === 'none') return 'none';
        const dir = (compound || 0) >= 0 ? 'pos' : 'neg';
        if (signal === 'strong') return `strong-${dir}`;
        if (signal === 'moderate') return `moderate-${dir}`;
        return 'weak';
    }

    function getRelativeTime(isoString) {
        if (!isoString) return '';
        try {
            const date = new Date(isoString);
            const now = new Date();
            const diffMs = now - date;
            const diffSec = Math.floor(diffMs / 1000);
            const diffMin = Math.floor(diffSec / 60);
            const diffHr = Math.floor(diffMin / 60);
            const diffDay = Math.floor(diffHr / 24);

            if (diffSec < 60) return 'just now';
            if (diffMin < 60) return `${diffMin}m ago`;
            if (diffHr < 24) return `${diffHr}h ago`;
            if (diffDay === 1) return 'yesterday';
            if (diffDay < 7) return `${diffDay}d ago`;
            if (diffDay < 30) return `${Math.floor(diffDay / 7)}w ago`;

            // Fallback to formatted date
            return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
        } catch (e) {
            return isoString;
        }
    }

    // =========================================================================
    // Initial Load
    // =========================================================================
    loadPreviousResults();
    loadTrends();
});
