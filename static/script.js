/**
 * TwitLysis v3 — Frontend Controller
 * Handles sidebar navigation, step timeline search UI, SSE streaming,
 * enriched trend/result cards, hashtag cloud, Chart.js lifecycle, memory cleanup,
 * v3: alias search, category chips, compare overlay, clusters, velocity, export.
 */
document.addEventListener('DOMContentLoaded', function () {

    // =========================================================================
    // Toast Notifications (replaces browser alert())
    // =========================================================================
    function showToast(message, type = 'success', duration = 3000) {
        const existing = document.getElementById('tl-toast');
        if (existing) existing.remove();

        const toast = document.createElement('div');
        toast.id = 'tl-toast';
        const iconMap = { success: 'fa-check-circle', error: 'fa-exclamation-circle', info: 'fa-info-circle' };
        toast.innerHTML = `<i class="fas ${iconMap[type] || 'fa-info-circle'}"></i> ${escapeHtmlBasic(message)}`;
        toast.style.cssText = [
            'position:fixed', 'bottom:32px', 'left:50%', 'transform:translateX(-50%) translateY(20px)',
            'background:var(--bg-elevated)', 'color:var(--text-primary)',
            'border:1px solid var(--border)', 'border-radius:30px',
            'padding:10px 22px', 'font-size:0.85rem', 'font-family:var(--font)',
            'box-shadow:0 8px 28px rgba(0,0,0,0.4)', 'z-index:9999',
            'display:flex', 'align-items:center', 'gap:8px',
            'transition:opacity 0.3s ease, transform 0.3s ease', 'opacity:0'
        ].join(';');
        const colorMap = { success: 'var(--success)', error: 'var(--error)', info: 'var(--primary)' };
        toast.querySelector('i').style.color = colorMap[type] || 'var(--primary)';
        document.body.appendChild(toast);

        // Animate in
        requestAnimationFrame(() => {
            toast.style.opacity = '1';
            toast.style.transform = 'translateX(-50%) translateY(0)';
        });

        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(-50%) translateY(12px)';
            setTimeout(() => toast.remove(), 350);
        }, duration);
    }

    // Simple HTML escaper for toast (before full escapeHtml is defined)
    function escapeHtmlBasic(str) {
        return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }

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
        'Scraping Top & Latest Tabs',
        'Saving Raw Tweets',
        '4-Signal Relevancy Scoring',
        'Clustering & Velocity Analysis',
        'Saving Results'
    ];
    let currentStepCards = [];
    let currentStepNum = 0;

    // Compare state
    let selectedForCompare = new Set();
    // Current term data cache for export/filter
    let _currentTermData = null;

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
            const batchToggle = document.getElementById('batch-checkbox');
            if (batchToggle && batchToggle.checked) {
                startBatchSearch();
            } else {
                startSearch();
            }
        }
    });

    searchButton.addEventListener('click', () => {
        const batchToggle = document.getElementById('batch-checkbox');
        if (batchToggle && batchToggle.checked) {
            startBatchSearch();
        } else {
            startSearch();
        }
    });

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
        const aliasChecked = document.getElementById('alias-checkbox')?.checked ? 'true' : 'false';
        activeEventSource = new EventSource(`/api/search?query=${encodeURIComponent(query)}&alias=${aliasChecked}`);

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

    // =========================================================================
    // Batch Search — Multi-term sequential analysis
    // =========================================================================
    function startBatchSearch() {
        const rawInput = searchQueryInput.value.trim();
        if (!rawInput) {
            searchStatus.textContent = 'Please enter comma-separated search terms';
            searchStatus.className = 'search-status error';
            return;
        }

        const terms = rawInput.split(',').map(t => t.trim()).filter(t => t.length > 0);
        if (terms.length < 1) {
            searchStatus.textContent = 'Please enter at least one search term';
            searchStatus.className = 'search-status error';
            return;
        }
        if (terms.length > 10) {
            searchStatus.textContent = 'Maximum 10 terms per batch';
            searchStatus.className = 'search-status error';
            return;
        }

        // Close any existing EventSource
        if (activeEventSource) {
            activeEventSource.close();
            activeEventSource = null;
        }

        // Reset UI
        searchStatus.textContent = `Batch analysis: ${terms.length} terms queued`;
        searchStatus.className = 'search-status';
        searchButton.disabled = true;
        resetTimeline();
        switchPanel('search-panel');

        const aliasChecked = document.getElementById('alias-checkbox')?.checked ? 'true' : 'false';
        activeEventSource = new EventSource(
            `/api/batch-search?terms=${encodeURIComponent(terms.join(','))}&alias=${aliasChecked}`
        );

        activeEventSource.onmessage = function (event) {
            try {
                const data = JSON.parse(event.data);
                if (data.error) {
                    appendRawLog(data.message, 'error');
                    searchStatus.textContent = 'Batch error occurred';
                    searchStatus.className = 'search-status error';
                    searchButton.disabled = false;
                    closeEventSource();
                    return;
                }

                const msg = data.message || '';

                // Detect step transitions within current term
                if (msg.includes('[STEP ')) {
                    try {
                        const stepNum = parseInt(msg.split('[STEP ')[1].split('/')[0]);
                        if (stepNum > currentStepNum) {
                            if (currentStepNum > 0) markStepDone(currentStepNum);
                            currentStepNum = stepNum;
                            const label = STEP_LABELS[stepNum - 1] || `Step ${stepNum}`;
                            createStepCard(stepNum, label);
                        }
                    } catch (e) { /* ignore */ }
                }

                // Detect batch transitions — reset timeline for each new term
                if (msg.includes('[BATCH ') && msg.includes('═══ Starting')) {
                    if (currentStepNum > 0) markStepDone(currentStepNum);
                    currentStepNum = 0;
                    // Don't fully reset — keep log visible
                    stepTimeline.innerHTML = '';
                    currentStepCards = [];
                    document.querySelectorAll('.step-segment').forEach(seg => {
                        seg.className = 'step-segment';
                        seg.querySelector('span').textContent = seg.dataset.step;
                    });
                }

                if (msg) {
                    const cls = classifyMessage(msg);
                    appendRawLog(msg, cls);
                    if (currentStepNum > 0 && !msg.includes('[STEP ') && !msg.includes('[START]') && !msg.includes('[INFO] This may take')) {
                        appendToStep(currentStepNum, msg, cls);
                    }
                }

                // Update batch progress in status bar
                if (msg.includes('[BATCH ') && msg.includes('/')) {
                    try {
                        const batchPart = msg.split('[BATCH ')[1].split(']')[0];
                        searchStatus.textContent = `Batch progress: ${batchPart}`;
                    } catch (e) { /* ignore */ }
                }

                if (data.progress === 100 || (msg && msg.includes('[BATCH COMPLETE]'))) {
                    if (currentStepNum > 0) markStepDone(currentStepNum);
                    searchButton.disabled = false;
                    searchStatus.textContent = `Batch complete! ${terms.length} terms analyzed.`;
                    searchStatus.className = 'search-status success';
                    closeEventSource();
                    setTimeout(() => {
                        loadPreviousResults();
                        loadTrends();
                    }, 800);
                }
            } catch (e) {
                console.error('Batch SSE parse error:', e);
            }
        };

        activeEventSource.onerror = function () {
            appendRawLog('[ERROR] Batch connection lost', 'error');
            searchStatus.textContent = 'Batch connection error';
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
                        <input type="checkbox" class="result-checkbox" data-term="${escapeHtml(result.term)}" title="Select for comparison">
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

                    // Compare checkbox
                    const chk = card.querySelector('.result-checkbox');
                    if (chk) {
                        chk.addEventListener('change', () => {
                            if (chk.checked) {
                                selectedForCompare.add(result.term);
                            } else {
                                selectedForCompare.delete(result.term);
                            }
                            updateCompareFab();
                        });
                    }
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
                _currentTermData = data;

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

                // Velocity badge
                renderVelocityBadge(data.velocity);

                // Velocity sparkline chart
                renderVelocityChart(data.velocity);

                // Cluster summary + accordion (pass all_tweets for browsing)
                renderClusters(data.clusters, data.all_tweets || []);

                // Language filter
                populateLanguageFilter(data.language_distribution, data.tweets);

                // Source filter
                populateSourceFilter(data.source_tab_breakdown, data.tweets);

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
        if (tweet.language) el.dataset.lang = tweet.language;
        if (tweet.source_tab) el.dataset.source = tweet.source_tab;

        const username = tweet.username || 'unknown';
        const score = tweet.relevancy_score || 0;
        const text = tweet.text || '';
        const url = tweet.tweet_url || '';
        const eng = tweet.engagement || {};
        const lang = tweet.language || 'en';
        const spamFlag = tweet.spam_flag || false;
        const influence = tweet.influence_score || 0;
        const sourceTab = tweet.source_tab || 'latest';
        // Flag overly long tweets (aggregate/spam pattern)
        const isLongForm = text.length > 800;

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

        // Source tab badge
        const sourceBadge = sourceTab === 'top'
            ? '<span class="source-badge source-top">⭐ Top</span>'
            : '<span class="source-badge source-latest">🔴 Live</span>';

        let badges = sourceBadge + `<span class="lang-badge">${lang}</span>`;
        if (spamFlag) badges += `<span class="spam-badge"><i class="fas fa-exclamation-triangle"></i> Spam</span>`;
        if (influence > 0.7) badges += `<span class="influence-badge"><i class="fas fa-bolt"></i> High Influence</span>`;
        if (isLongForm) badges += `<span class="spam-badge" title="This tweet is unusually long — may be an aggregate/digest post"><i class="fas fa-align-left"></i> Long-form</span>`;

        el.innerHTML = `
            <p class="tweet-text">${escapeHtml(text)}</p>
            <div class="tweet-meta">
                <span class="tweet-username">${escapeHtml(username)}</span>
                <span class="tweet-score">Relevancy: ${score}%</span>
                ${badges}
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
    // Velocity Badge + Sparkline Chart
    // =========================================================================
    function renderVelocityBadge(velocity) {
        const container = document.getElementById('velocity-badge');
        if (!container) return;
        if (!velocity || !velocity.trend_direction || velocity.trend_direction === 'insufficient_data') {
            container.innerHTML = '';
            return;
        }
        const icons = { surging: 'fa-rocket', growing: 'fa-arrow-trend-up', steady: 'fa-minus', fading: 'fa-arrow-trend-down' };
        const dir = velocity.trend_direction;
        container.innerHTML = `
            <span class="velocity-badge ${dir}">
                <i class="fas ${icons[dir] || 'fa-minus'}"></i>
                ${capitalize(dir)}
                <span class="velocity-tpm">${velocity.velocity_tpm || 0} tpm</span>
            </span>
        `;
    }

    function renderVelocityChart(velocity) {
        const container = document.getElementById('velocity-chart-container');
        if (!container) return;
        if (!velocity || !velocity.timeline_buckets || velocity.timeline_buckets.length < 2) {
            container.style.display = 'none';
            return;
        }
        container.style.display = 'block';
        destroyChart('velocity-sparkline-chart');

        const labels = velocity.timeline_buckets.map(b => b.time);
        const counts = velocity.timeline_buckets.map(b => b.count);

        chartInstances['velocity-sparkline-chart'] = new Chart(
            document.getElementById('velocity-sparkline-chart'), {
            type: 'line',
            data: {
                labels,
                datasets: [{
                    data: counts,
                    borderColor: '#1da1f2',
                    backgroundColor: 'rgba(29,161,242,0.1)',
                    fill: true,
                    tension: 0.4,
                    pointRadius: 2,
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { ticks: { color: '#536471', font: { size: 10 } }, grid: { display: false } },
                    y: { ticks: { color: '#536471', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.04)' }, beginAtZero: true }
                }
            }
        });
    }

    // =========================================================================
    // Clusters
    // =========================================================================
    function renderClusters(clusterData, allTweets) {
        const section = document.getElementById('clusters-section');
        const accordion = document.getElementById('clusters-accordion');
        const summary = document.getElementById('cluster-summary');
        if (!section || !accordion) return;

        if (!clusterData || !clusterData.clusters || clusterData.clusters.length <= 1) {
            section.style.display = 'none';
            if (summary) summary.innerHTML = '';
            return;
        }

        if (summary && clusterData.summary) {
            summary.innerHTML = `<i class="fas fa-project-diagram" style="margin-right:6px;"></i>${escapeHtml(clusterData.summary)}`;
        }

        section.style.display = 'block';
        accordion.innerHTML = '';
        const frag = document.createDocumentFragment();

        clusterData.clusters.forEach(cluster => {
            const card = document.createElement('div');
            card.className = 'cluster-card';

            // Build tweet list HTML for this cluster
            let clusterTweetsHtml = '';
            if (allTweets && allTweets.length > 0 && cluster.tweet_indices) {
                const clusterTweets = cluster.tweet_indices
                    .map(idx => allTweets.find(t => t.index === idx))
                    .filter(Boolean)
                    .sort((a, b) => (b.relevancy_score || 0) - (a.relevancy_score || 0))
                    .slice(0, 10);  // Show top 10 per cluster

                if (clusterTweets.length > 0) {
                    clusterTweetsHtml = `<div class="cluster-tweets-list">
                        ${clusterTweets.map(t => {
                            const eng = t.engagement || {};
                            const url = t.tweet_url || '#';
                            return `<div class="cluster-tweet-item">
                                <p class="cluster-tweet-text">${escapeHtml(t.text)}</p>
                                <div class="cluster-tweet-meta">
                                    <span class="cluster-tweet-user">${escapeHtml(t.username)}</span>
                                    <span class="relevancy-badge">${t.relevancy_score}%</span>
                                    <span class="lang-badge">${t.language || 'en'}</span>
                                    ${t.spam_flag ? '<span class="spam-badge"><i class="fas fa-exclamation-triangle"></i></span>' : ''}
                                    <span class="cluster-tweet-eng">
                                        <i class="far fa-comment"></i> ${eng.replies || 0}
                                        <i class="fas fa-retweet"></i> ${eng.retweets || 0}
                                        <i class="far fa-heart"></i> ${eng.likes || 0}
                                    </span>
                                    ${url !== '#' ? `<a href="${url}" target="_blank" class="view-tweet-link"><i class="fas fa-external-link-alt"></i></a>` : ''}
                                </div>
                            </div>`;
                        }).join('')}
                    </div>`;
                }
            }

            card.innerHTML = `
                <div class="cluster-header">
                    <span class="cluster-label">${escapeHtml(cluster.label)}</span>
                    <div class="cluster-meta">
                        <span class="cluster-pct">${cluster.percentage}% (${cluster.count})</span>
                        <div class="cluster-bar"><div class="cluster-bar-fill" style="width:${cluster.percentage}%"></div></div>
                        <i class="fas fa-chevron-down cluster-chevron"></i>
                    </div>
                </div>
                <div class="cluster-body">
                    <div class="cluster-keywords">
                        ${(cluster.keywords || []).map(k => `<span class="cluster-keyword-tag">${escapeHtml(k)}</span>`).join('')}
                    </div>
                    ${clusterTweetsHtml || `<span class="cluster-tweet-count">${cluster.count} tweets in this cluster</span>`}
                </div>
            `;
            card.querySelector('.cluster-header').addEventListener('click', () => {
                card.classList.toggle('expanded');
            });
            frag.appendChild(card);
        });
        accordion.appendChild(frag);
    }

    // =========================================================================
    // Language Filter
    // =========================================================================
    function populateLanguageFilter(langDist, tweets) {
        const sel = document.getElementById('language-filter');
        if (!sel) return;

        // Reset
        while (sel.options.length > 1) sel.remove(1);

        if (langDist && Object.keys(langDist).length > 1) {
            const sorted = Object.entries(langDist).sort((a, b) => b[1] - a[1]);
            sorted.forEach(([lang, count]) => {
                const opt = document.createElement('option');
                opt.value = lang;
                opt.textContent = `${lang.toUpperCase()} (${count})`;
                sel.appendChild(opt);
            });
        }

        if (!sel._hasFilterListener) {
            sel.addEventListener('change', () => {
                const filter = sel.value;
                const container = document.getElementById('selected-tweets');
                const tweetElements = container.querySelectorAll('.tweet');
                tweetElements.forEach(el => {
                    if (filter === 'all' || el.dataset.lang === filter) {
                        el.style.display = '';
                    } else {
                        el.style.display = 'none';
                    }
                });
            });
            sel._hasFilterListener = true;
        }
        sel.value = 'all';
    }

    // =========================================================================
    // Source Tab Filter
    // =========================================================================
    function populateSourceFilter(sourceBreakdown, tweets) {
        const sel = document.getElementById('source-filter');
        if (!sel) return;

        // Update option labels with counts
        if (sourceBreakdown) {
            const topOpt = sel.querySelector('option[value="top"]');
            const latestOpt = sel.querySelector('option[value="latest"]');
            if (topOpt) topOpt.textContent = `⭐ Top (${sourceBreakdown.top || 0})`;
            if (latestOpt) latestOpt.textContent = `🔴 Latest (${sourceBreakdown.latest || 0})`;
        }

        if (!sel._hasSourceFilterListener) {
            sel.addEventListener('change', () => {
                const filter = sel.value;
                const container = document.getElementById('selected-tweets');
                const tweetElements = container.querySelectorAll('.tweet');
                tweetElements.forEach(el => {
                    if (filter === 'all' || el.dataset.source === filter) {
                        el.style.display = '';
                    } else {
                        el.style.display = 'none';
                    }
                });
            });
            sel._hasSourceFilterListener = true;
        }
        sel.value = 'all';
    }

    // =========================================================================
    // Compare
    // =========================================================================
    function updateCompareFab() {
        const fab = document.getElementById('compare-fab');
        const count = document.getElementById('compare-count');
        if (selectedForCompare.size >= 2) {
            fab.style.display = 'block';
            count.textContent = selectedForCompare.size;
        } else {
            fab.style.display = 'none';
        }
    }

    document.getElementById('compare-fab')?.addEventListener('click', () => {
        if (selectedForCompare.size < 2) return;
        loadComparison(Array.from(selectedForCompare));
    });

    document.getElementById('close-compare')?.addEventListener('click', () => {
        document.getElementById('compare-overlay').style.display = 'none';
    });

    function loadComparison(terms) {
        const overlay = document.getElementById('compare-overlay');
        const content = document.getElementById('compare-content');
        overlay.style.display = 'block';
        content.innerHTML = '<div class="loading-spinner"><i class="fas fa-spinner fa-spin"></i> Loading comparison...</div>';

        fetch(`/api/compare?terms=${encodeURIComponent(terms.join(','))}`)
            .then(r => r.json())
            .then(data => {
                if (data.error) {
                    content.innerHTML = `<p class="no-results">${escapeHtml(data.error)}</p>`;
                    return;
                }
                let html = '<div class="compare-grid">';
                (data.terms || []).forEach(t => {
                    const vel = t.velocity || {};
                    html += `
                        <div class="compare-card">
                            <h3>${escapeHtml(t.term)}</h3>
                            <div class="compare-stat"><span class="label">Tweets</span><span class="value">${t.tweet_count}</span></div>
                            <div class="compare-stat"><span class="label">Trend Score</span><span class="value">${t.trend_score}/100</span></div>
                            <div class="compare-stat"><span class="label">Sentiment</span><span class="value">${capitalize(t.sentiment?.signal_strength || 'N/A')} (${(t.sentiment?.avg_compound || 0) > 0 ? '+' : ''}${t.sentiment?.avg_compound || 0})</span></div>
                            <div class="compare-stat"><span class="label">Velocity</span><span class="value">${capitalize(vel.trend_direction || 'N/A')} (${vel.velocity_tpm || 0} tpm)</span></div>
                            <div class="compare-stat"><span class="label">Total Likes</span><span class="value">${formatNum(t.total_engagement?.likes || 0)}</span></div>
                            <div class="compare-stat"><span class="label">Total Retweets</span><span class="value">${formatNum(t.total_engagement?.retweets || 0)}</span></div>
                        </div>
                    `;
                });
                html += '</div>';

                // Shared hashtags
                if (data.shared_hashtags && data.shared_hashtags.length) {
                    html += '<div class="compare-card"><h3>Shared Hashtags</h3><div style="display:flex;flex-wrap:wrap;gap:6px;">';
                    data.shared_hashtags.forEach(h => { html += `<span class="hashtag-pill">${escapeHtml(h)}</span>`; });
                    html += '</div></div>';
                }

                content.innerHTML = html;
            })
            .catch(err => {
                content.innerHTML = `<p class="no-results">Failed to load comparison</p>`;
                console.error('Compare error:', err);
            });
    }

    // =========================================================================
    // Category Chips
    // =========================================================================
    function loadCategories() {
        fetch('/api/categories')
            .then(r => r.json())
            .then(data => {
                const container = document.getElementById('category-chips');
                if (!container) return;
                container.innerHTML = '';
                const frag = document.createDocumentFragment();
                Object.entries(data).forEach(([category, info]) => {
                    const chip = document.createElement('button');
                    chip.className = 'category-chip';
                    chip.innerHTML = `<span class="chip-icon">${info.icon || '🔍'}</span> ${escapeHtml(category)}`;
                    chip.title = `${(info.terms || []).length} terms`;
                    chip.addEventListener('click', () => {
                        const terms = info.terms || [];
                        if (terms.length > 0) {
                            const randomTerm = terms[Math.floor(Math.random() * terms.length)];
                            searchQueryInput.value = randomTerm;
                            searchQueryInput.focus();
                        }
                    });
                    frag.appendChild(chip);
                });
                container.appendChild(frag);
            })
            .catch(() => {});
    }

    // =========================================================================
    // Export
    // =========================================================================
    const exportBtn = document.getElementById('export-btn');
    const exportMenu = document.getElementById('export-menu');

    if (exportBtn) {
        exportBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            exportMenu.style.display = exportMenu.style.display === 'none' ? 'block' : 'none';
        });
    }
    document.addEventListener('click', () => {
        if (exportMenu) exportMenu.style.display = 'none';
    });

    if (exportMenu) {
        exportMenu.querySelectorAll('button[data-format]').forEach(btn => {
            btn.addEventListener('click', () => {
                const format = btn.dataset.format;
                const term = document.getElementById('term-select')?.value;
                if (!term) return;
                handleExport(term, format);
                exportMenu.style.display = 'none';
            });
        });
    }

    function handleExport(term, format) {
        const url = `/api/export?term=${encodeURIComponent(term)}&format=${format}`;

        if (format === 'csv' || format === 'json') {
            // Direct download
            if (format === 'csv') {
                window.location.href = url;
            } else {
                fetch(url).then(r => r.blob()).then(blob => {
                    const a = document.createElement('a');
                    a.href = URL.createObjectURL(blob);
                    a.download = `${term}_export.json`;
                    a.click();
                    URL.revokeObjectURL(a.href);
                });
            }
        } else if (format === 'md') {
            fetch(url).then(r => r.json()).then(data => {
                if (data.markdown) {
                    navigator.clipboard.writeText(data.markdown)
                        .then(() => showToast('Markdown report copied to clipboard!', 'success'))
                        .catch(() => showToast('Clipboard access denied — check browser permissions', 'error'));
                }
            });
        } else if (format === 'html') {
            fetch(url).then(r => r.json()).then(data => {
                const htmlContent = `<!DOCTYPE html><html><head><meta charset="UTF-8"><title>TwitLysis Report: ${escapeHtml(data.term || term)}</title><style>body{font-family:Inter,sans-serif;background:#0e1621;color:#e7e9ea;padding:40px;max-width:800px;margin:0 auto}.header{border-bottom:1px solid #2f3336;padding-bottom:20px;margin-bottom:20px}h1{color:#1da1f2;font-size:1.6rem}.stat{display:inline-block;margin-right:20px;font-size:0.9rem;color:#8899a6}.tweet{background:rgba(25,39,52,0.7);border:1px solid rgba(255,255,255,0.06);border-radius:12px;padding:16px;margin-bottom:12px}.score{color:#1da1f2;font-weight:600}</style></head><body><div class="header"><h1>TwitLysis Report: "${escapeHtml(data.term || term)}"</h1><div><span class="stat">Score: ${data.trend_score}/100</span><span class="stat">Tweets: ${data.tweet_count}</span></div></div>${(data.top_tweets || []).map(t => `<div class="tweet"><p>${escapeHtml(t.text || '')}</p><div><span class="score">[${t.score}%]</span> ${escapeHtml(t.username || '')}</div></div>`).join('')}<p style="color:#536471;margin-top:30px;font-size:0.8rem">Generated by TwitLysis • ${new Date().toLocaleDateString()}</p></body></html>`;
                const blob = new Blob([htmlContent], { type: 'text/html' });
                const a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = `${term}_report.html`;
                a.click();
                URL.revokeObjectURL(a.href);
            });
        }
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
    loadCategories();
});
